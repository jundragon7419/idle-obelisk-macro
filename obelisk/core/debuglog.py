"""로그 기록과 디버그 화면 저장.

문제 로그(problem=True)에는 Debug 여부와 상관없이 '[!]'를 붙인다.

Debug가 켜져 있으면 로그마다 그 순간 화면을 메모리에 쌓아 둔다.
한 번의 작업 단위(begin ~ end, 예: 루트버그 한 주기) 안에서 문제 로그가 나오면
그 단위의 앞선 화면부터 끝날 때까지의 화면을 debug 폴더에 '로그ID.png'로 저장하고,
문제 없이 끝나면 쌓아 둔 화면을 버린다.

쌓아 둘 때는 PNG로 압축해 둔다 (원본 2.7MB → 약 0.2MB). 앞 로그와 같은 화면이면
압축본을 함께 쓴다.
"""
import threading
from typing import Callable

import cv2

from ..paths import DEBUG_DIR

MAX_BUFFER = 60   # 한 작업 단위에서 쌓아 둘 최대 화면 수 (넘으면 오래된 것부터 버림)
PROBLEM_MARK = "[!] "


class DebugLogger:
    def __init__(self, cfg: dict, raw_log: Callable[[str], str], prefix: str = ""):
        """raw_log(msg)는 로그를 남기고 로그 ID를 돌려준다."""
        self.cfg, self.raw_log, self.prefix = cfg, raw_log, prefix
        self.adb = None  # 연결되면 설정
        self._lock = threading.Lock()
        self._buffer: list[tuple[str, str, bytes]] = []    # (로그 ID, 메시지, PNG)
        self._last_src = None                               # 직전에 압축한 화면 (같은 화면 재사용)
        self._last_png = b""
        self._problem = False                               # 이번 작업 단위에 문제가 있었는지
        self._saved = False                                 # 이번 작업 단위에서 저장을 시작했는지

    @property
    def debug(self) -> bool:
        return bool(self.cfg["general"].get("debug")) and self.adb is not None

    def __call__(self, msg: str, problem: bool = False) -> str:
        msg = f"{PROBLEM_MARK if problem else ''}{self.prefix}{msg}"
        log_id = self.raw_log(msg)
        if not self.debug:
            return log_id
        try:
            frame = self.adb.current_frame()
        except Exception as e:  # 캡처 실패가 매크로를 멈추면 안 됨
            self.raw_log(f"디버그 화면 캡처 실패: {e}")
            return log_id
        with self._lock:
            if frame is not self._last_src:
                ok, buf = cv2.imencode(".png", frame, [cv2.IMWRITE_PNG_COMPRESSION, 1])
                self._last_src, self._last_png = frame, (buf.tobytes() if ok else b"")
            self._buffer.append((log_id, msg, self._last_png))
            if len(self._buffer) > MAX_BUFFER:
                self._buffer.pop(0)
            if problem:
                self._problem = True
            if self._problem:
                self._flush_locked()
        return log_id

    # ── 작업 단위 ────────────────────────────────
    def begin(self):
        with self._lock:
            self._buffer.clear()
            self._last_src, self._last_png = None, b""
            self._problem = self._saved = False

    def end(self):
        """문제가 없었으면 쌓아 둔 화면을 버린다 (문제가 있었으면 이미 저장됨)."""
        with self._lock:
            self._buffer.clear()
            self._last_src, self._last_png = None, b""
            self._problem = self._saved = False

    def _flush_locked(self):
        if not self._buffer:
            return
        try:
            DEBUG_DIR.mkdir(exist_ok=True)
            with open(DEBUG_DIR / "debug.log", "a", encoding="utf-8") as f:
                if not self._saved:
                    f.write("----\n")  # 작업 단위 구분
                    self._saved = True
                for log_id, msg, png in self._buffer:
                    if png:
                        (DEBUG_DIR / f"{log_id}.png").write_bytes(png)
                    f.write(f"{log_id}\t{msg}\n")
        except Exception as e:
            self.raw_log(f"디버그 화면 저장 실패: {e}")
        self._buffer.clear()
