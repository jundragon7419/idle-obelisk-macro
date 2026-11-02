"""수치 기록: 이번 실행분과 누적분.

누적분은 stats.json(git 제외)에 저장해서 앱을 껐다 켜도 유지한다.
값은 '기능.항목' 경로로 센다. 예: add("lootbug.looted"), add("lootbug.buffs.game_speed")
"""
import json
import threading
import time
from datetime import datetime

from ..paths import APP_ROOT

STATS_PATH = APP_ROOT / "stats.json"
SAVE_INTERVAL = 5.0  # 초. 자주 쓰지 않도록 모아서 저장


def _bump(d: dict, path: list[str], n: int):
    for k in path[:-1]:
        d = d.setdefault(k, {})
    d[path[-1]] = d.get(path[-1], 0) + n


def _get(d: dict, path: list[str], default=None):
    for k in path:
        if not isinstance(d, dict) or k not in d:
            return default
        d = d[k]
    return d


class Stats:
    def __init__(self):
        self._lock = threading.Lock()
        self.session: dict = {}
        self.total: dict = self._load()
        self.session_started: float | None = None   # time.monotonic()
        self.session_ended: float | None = None
        self._dirty = False
        self._last_save = 0.0

    @staticmethod
    def _load() -> dict:
        try:
            return json.loads(STATS_PATH.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    # ── 기록 ─────────────────────────────────────
    def start_session(self):
        with self._lock:
            self.session = {}
            self.session_started = time.monotonic()
            self.session_ended = None

    def end_session(self):
        with self._lock:
            self.session_ended = time.monotonic()
        self.save(force=True)

    def elapsed(self) -> float | None:
        """이번 실행 시간. 정지한 뒤에는 마지막 실행 시간을 그대로 보여준다."""
        if self.session_started is None:
            return None
        return (self.session_ended or time.monotonic()) - self.session_started

    def add(self, key: str, n: int = 1):
        path = key.split(".")
        with self._lock:
            _bump(self.session, path, n)
            _bump(self.total, path, n)
            self._dirty = True
        self.save()

    def mark(self, key: str):
        """마지막 수령 시각 같은 시각 값 기록."""
        path = key.split(".")
        now = datetime.now().isoformat(timespec="seconds")
        with self._lock:
            for d in (self.session, self.total):
                node = d
                for k in path[:-1]:
                    node = node.setdefault(k, {})
                node[path[-1]] = now
            self._dirty = True
        self.save()

    def reset_total(self):
        with self._lock:
            self.total = {}
            self._dirty = True
        self.save(force=True)

    # ── 조회 ─────────────────────────────────────
    def get(self, scope: str, key: str, default=0):
        with self._lock:
            return _get(self.session if scope == "session" else self.total,
                        key.split("."), default)

    def keys_under(self, key: str) -> list[str]:
        """이번 실행과 누적에 나온 하위 항목 이름 (예: 구매한 버프 목록)."""
        with self._lock:
            names = set()
            for d in (self.session, self.total):
                node = _get(d, key.split("."), {})
                if isinstance(node, dict):
                    names.update(node)
            return sorted(names)

    # ── 저장 ─────────────────────────────────────
    def save(self, force: bool = False):
        with self._lock:
            if not self._dirty:
                return
            if not force and time.monotonic() - self._last_save < SAVE_INTERVAL:
                return
            data = json.dumps(self.total, ensure_ascii=False, indent=2)
            self._dirty = False
            self._last_save = time.monotonic()
        try:
            STATS_PATH.write_text(data, encoding="utf-8")
        except OSError:
            pass
