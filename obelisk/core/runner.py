"""켜진 기능들을 각자의 주기로 돌리는 실행 스레드."""
import threading
import time
import traceback
from typing import Callable

from ..features import FEATURES
from ..features.base import Context
from .adb import Adb, AdbError, ConfigError
from .debuglog import DebugLogger
from .health import LOG_DIR, HealthMonitor, append_rotated
from .stats import Stats

MAX_STREAK = 10   # 연속으로 즉시 재실행하는 최대 횟수 (무한 반복 방지)
MAX_ERRORS = 5    # 같은 기능에서 예상하지 못한 오류가 연속으로 나면 멈춤


class Stopped(Exception):
    pass


class MacroRunner(threading.Thread):
    def __init__(self, cfg: dict, log: Callable[[str], str], stats: Stats | None = None):
        """log(msg)는 로그를 남기고 그 로그 ID를 돌려준다."""
        super().__init__(daemon=True)
        self.cfg = cfg
        self.stats = stats
        self.next_due: dict[str, float] = {}   # 기능별 다음 확인 시각 (monotonic)
        self.current: str | None = None        # 지금 실행 중인 기능
        self.log = DebugLogger(cfg, log)
        self._stop_event = threading.Event()
        self.features = []
        self.adb: Adb | None = None
        self.health: HealthMonitor | None = None

    def stop(self):
        self._stop_event.set()

    def _sleep(self, sec: float):
        if self._stop_event.wait(sec):
            raise Stopped

    def run(self):
        try:
            a = self.cfg["adb"]
            self.adb = Adb(a["path"], a.get("serial", ""), int(a.get("tap_press_ms", 0)),
                           log=self.log, sleep=self._sleep)
            self.log.adb = self.adb
            mode = self.cfg["general"].get("capture", "raw")
            if mode == "stream" and self.adb.start_stream():
                self.log(f"ADB 연결: {self.adb.serial} (연속 캡처)")
            else:
                self.log(f"ADB 연결: {self.adb.serial} (일반 캡처)")
            # 메모리 경고는 다른 스레드에서 나오므로 진행 중인 작업의 디버그 화면 저장을 일으키지 않게 함
            raw = self.log.raw_log
            health_log = lambda m, problem=False: raw(("[!] " if problem else "") + m)
            self.health = HealthMonitor(self.cfg, health_log, lambda: self.adb.capture_count,
                                        self._critical)
            self.health.start()
            ctx = Context(self.adb, self.cfg, self.log, self._sleep, self.stats)
            self.features = [F(ctx) for F in FEATURES if F.implemented]
            self._loop()
        except Stopped:
            pass
        except AdbError as e:
            self.log(f"시작 실패: {e}", problem=True)
        except Exception as e:  # GUI가 멈추지 않도록 로그로 남김
            self._write_traceback()
            self.log(f"예상하지 못한 오류로 멈춥니다: {type(e).__name__}: {e}. "
                     "자세한 내용: logs/error.log", problem=True)
        finally:
            if self.health is not None:
                self.health.stop()
            if self.adb is not None:
                self.adb.close()
        self.log("정지됨")

    def _critical(self, reason: str):
        """메모리가 위험할 때 감시 스레드가 부른다."""
        self.log(f"{reason}. 매크로를 멈춥니다.", problem=True)
        self.log("    LD플레이어가 쓰던 메모리는 LD플레이어를 다시 시작해야 돌아옵니다. "
                 "재시작 후 다시 Run을 눌러 주세요. 기록: logs/memory.jsonl", problem=True)
        self.stop()

    @staticmethod
    def _write_traceback():
        try:
            append_rotated(LOG_DIR / "error.log", traceback.format_exc())
        except OSError:
            pass

    def _loop(self):
        next_due = self.next_due
        next_due.update({f.key: 0.0 for f in self.features})
        streak = {f.key: 0 for f in self.features}
        errors = {f.key: 0 for f in self.features}
        while not self._stop_event.is_set():
            active = [f for f in self.features if f.enabled]
            if not active:
                self._sleep(1.0)
                continue
            now = time.monotonic()
            for f in active:
                if now < next_due[f.key]:
                    continue
                self.current = f.key
                self.log.begin()
                try:
                    handled = f.run_once()
                    errors[f.key] = 0
                except (Stopped, ConfigError):
                    raise
                except AdbError as e:
                    f.log(f"ADB 오류로 이번 주기를 건너뜁니다: {e}", problem=True)
                    handled = False
                except Exception as e:
                    # 한 기능의 오류가 실행 전체를 멈추지 않도록 이번 주기만 건너뜀
                    errors[f.key] += 1
                    if errors[f.key] >= MAX_ERRORS:
                        raise   # 바깥에서 기록하고 멈춤
                    self._write_traceback()
                    f.log(f"예상하지 못한 오류로 이번 주기를 건너뜁니다 ({errors[f.key]}/{MAX_ERRORS}): "
                          f"{type(e).__name__}: {e}. 자세한 내용: logs/error.log", problem=True)
                    handled = False
                finally:
                    self.log.end()
                    self.current = None
                if handled and streak[f.key] < MAX_STREAK:
                    streak[f.key] += 1
                    next_due[f.key] = time.monotonic()
                else:
                    streak[f.key] = 0
                    next_due[f.key] = time.monotonic() + f.interval
            wait = min(next_due[f.key] for f in active) - time.monotonic()
            self._sleep(max(0.1, min(wait, 1.0)))
