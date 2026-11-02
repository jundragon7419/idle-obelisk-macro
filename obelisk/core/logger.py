"""로그 ID 생성과 로그 줄 형식.

ID는 '연월일시분초(yyMMddHHmmss) + 그 초 안의 순번(01부터)'을 이어 붙인 정수를
16진수 대문자로 바꾼 값이다.
  2026-11-02 20:49:35의 첫 로그 → 26110220493501 → 17BF426AE2BD
같은 초에 로그가 100개를 넘으면 순번이 세 자리가 되어 숫자가 길어질 뿐 중복되지는 않는다.
"""
import threading
from datetime import datetime


class LogIdGenerator:
    def __init__(self):
        self._lock = threading.Lock()
        self._last_sec = ""
        self._seq = 0

    def next(self, now: datetime | None = None) -> tuple[str, datetime]:
        now = now or datetime.now()
        sec = now.strftime("%y%m%d%H%M%S")
        with self._lock:
            if sec == self._last_sec:
                self._seq += 1
            else:
                self._last_sec, self._seq = sec, 1
            raw = int(f"{sec}{self._seq:02d}")
        return format(raw, "X"), now


def decode(log_id: str) -> str:
    """16진수 로그 ID를 원래 숫자(yyMMddHHmmss + 순번)로 되돌린다."""
    return str(int(log_id, 16))
