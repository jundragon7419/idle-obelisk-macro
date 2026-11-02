"""로그를 남기면서, 디버그가 켜져 있으면 그 순간 화면을 로그 ID 이름으로 저장한다."""
from typing import Callable

from ..paths import DEBUG_DIR
from .imaging import imwrite


class DebugLogger:
    def __init__(self, cfg: dict, raw_log: Callable[[str], str], prefix: str = ""):
        """raw_log(msg)는 로그를 남기고 로그 ID를 돌려준다."""
        self.cfg, self.raw_log, self.prefix = cfg, raw_log, prefix
        self.adb = None  # 연결되면 설정

    def __call__(self, msg: str) -> str:
        msg = f"{self.prefix}{msg}"
        log_id = self.raw_log(msg)
        if self.cfg["general"].get("debug") and self.adb is not None:
            try:
                DEBUG_DIR.mkdir(exist_ok=True)
                imwrite(DEBUG_DIR / f"{log_id}.png", self.adb.current_frame())
                with open(DEBUG_DIR / "debug.log", "a", encoding="utf-8") as f:
                    f.write(f"{log_id}\t{msg}\n")
            except Exception as e:  # 디버그 저장 실패가 매크로를 멈추면 안 됨
                self.raw_log(f"디버그 스크린샷 저장 실패: {e}")
        return log_id
