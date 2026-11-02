"""켜진 기능들을 각자의 주기로 돌리는 실행 스레드."""
import threading
import time
from typing import Callable

from ..features import FEATURES
from ..features.base import Context
from ..paths import DEBUG_DIR
from .adb import Adb, AdbError
from .imaging import imwrite

MAX_STREAK = 10  # 연속으로 즉시 재실행하는 최대 횟수 (무한 반복 방지)


class Stopped(Exception):
    pass


class MacroRunner(threading.Thread):
    def __init__(self, cfg: dict, log: Callable[[str], str]):
        """log(msg)는 로그를 남기고 그 로그 ID를 돌려준다."""
        super().__init__(daemon=True)
        self.cfg, self._raw_log = cfg, log
        self._stop_event = threading.Event()
        self.features = []
        self.adb: Adb | None = None

    def log(self, msg: str) -> str:
        """로그를 남기고, 디버그가 켜져 있으면 그 순간 화면을 로그 ID 이름으로 저장한다."""
        log_id = self._raw_log(msg)
        if self.cfg["general"].get("debug") and self.adb is not None:
            try:
                DEBUG_DIR.mkdir(exist_ok=True)
                imwrite(DEBUG_DIR / f"{log_id}.png", self.adb.current_frame())
                with open(DEBUG_DIR / "debug.log", "a", encoding="utf-8") as f:
                    f.write(f"{log_id}\t{msg}\n")
            except Exception as e:  # 디버그 저장 실패가 매크로를 멈추면 안 됨
                self._raw_log(f"디버그 스크린샷 저장 실패: {e}")
        return log_id

    def stop(self):
        self._stop_event.set()

    def _sleep(self, sec: float):
        if self._stop_event.wait(sec):
            raise Stopped

    def run(self):
        try:
            a = self.cfg["adb"]
            self.adb = Adb(a["path"], a.get("serial", ""), int(a.get("tap_press_ms", 0)))
            self.log(f"ADB 연결: {self.adb.serial}")
            ctx = Context(self.adb, self.cfg, self.log, self._sleep)
            self.features = [F(ctx) for F in FEATURES if F.implemented]
            self._loop()
        except Stopped:
            pass
        except AdbError as e:
            self.log(f"시작 실패: {e}")
        except Exception as e:  # GUI가 멈추지 않도록 로그로 남김
            self.log(f"예상하지 못한 오류로 멈춥니다: {type(e).__name__}: {e}")
        self.log("정지됨")

    def _loop(self):
        next_due = {f.key: 0.0 for f in self.features}
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
                try:
                    handled = f.run_once()
                except AdbError as e:
                    f.log(f"ADB 오류: {e}")
                    handled = False
                if handled and streak[f.key] < MAX_STREAK:
                    streak[f.key] += 1
                    next_due[f.key] = time.monotonic()
                else:
                    streak[f.key] = 0
                    next_due[f.key] = time.monotonic() + f.interval
            wait = min(next_due[f.key] for f in active) - time.monotonic()
            self._sleep(max(0.1, min(wait, 1.0)))
