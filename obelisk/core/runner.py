"""켜진 기능들을 각자의 주기로 돌리는 실행 스레드."""
import threading
import time
from typing import Callable

from ..features import FEATURES
from ..features.base import Context
from .adb import Adb, AdbError
from .debuglog import DebugLogger
from .stats import Stats

MAX_STREAK = 10  # 연속으로 즉시 재실행하는 최대 횟수 (무한 반복 방지)


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

    def stop(self):
        self._stop_event.set()

    def _sleep(self, sec: float):
        if self._stop_event.wait(sec):
            raise Stopped

    def run(self):
        try:
            a = self.cfg["adb"]
            self.adb = Adb(a["path"], a.get("serial", ""), int(a.get("tap_press_ms", 0)))
            self.log.adb = self.adb
            self.log(f"ADB 연결: {self.adb.serial}")
            ctx = Context(self.adb, self.cfg, self.log, self._sleep, self.stats)
            self.features = [F(ctx) for F in FEATURES if F.implemented]
            self._loop()
        except Stopped:
            pass
        except AdbError as e:
            self.log(f"시작 실패: {e}", problem=True)
        except Exception as e:  # GUI가 멈추지 않도록 로그로 남김
            self.log(f"예상하지 못한 오류로 멈춥니다: {type(e).__name__}: {e}", problem=True)
        self.log("정지됨")

    def _loop(self):
        next_due = self.next_due
        next_due.update({f.key: 0.0 for f in self.features})
        streak = {f.key: 0 for f in self.features}
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
                except AdbError as e:
                    f.log(f"ADB 오류: {e}", problem=True)
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
