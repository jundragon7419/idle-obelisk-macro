"""메모리 감시: 매크로, LD플레이어, 시스템 메모리를 주기적으로 잰다.

LD플레이어는 캡처를 반복하면 가상 머신 프로세스(Ld9BoxHeadless.exe) 메모리가 늘어날 수 있다.
측정값은 logs/memory.jsonl에 남기고(1MB마다 새 파일), 남은 메모리가 기준보다 적으면
경고하거나 매크로를 멈춘다. 매크로를 멈춰도 LD플레이어가 쓰던 메모리는 LD플레이어를
다시 시작해야 돌아온다.
"""
import json
import os
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Callable

from ..paths import APP_ROOT

LOG_DIR = APP_ROOT / "logs"
LDPLAYER_NAMES = ("ld9boxheadless.exe", "ldboxheadless.exe", "dnplayer.exe")


@dataclass
class Snapshot:
    time: str
    macro_mb: float
    ldplayer_mb: float | None     # LD플레이어 관련 프로세스 합계 (없으면 None)
    system_percent: float
    available_mb: float
    captures: int


def append_rotated(path, text: str, limit: int = 1 << 20):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size >= limit:
        path.replace(path.with_suffix(path.suffix + ".1"))
    with open(path, "a", encoding="utf-8") as f:
        f.write(text + "\n")


def take_snapshot(captures: int = 0) -> Snapshot | None:
    try:
        import psutil
    except ImportError:
        return None
    mb = 1024 * 1024
    own = psutil.Process(os.getpid()).memory_info().rss / mb
    ld = 0.0
    found = False
    for p in psutil.process_iter(["name", "memory_info"]):
        name = (p.info.get("name") or "").lower()
        if name in LDPLAYER_NAMES and p.info.get("memory_info"):
            ld += p.info["memory_info"].rss / mb
            found = True
    vm = psutil.virtual_memory()
    return Snapshot(datetime.now().isoformat(timespec="seconds"), round(own, 1),
                    round(ld, 1) if found else None, vm.percent, round(vm.available / mb, 1),
                    captures)


class HealthMonitor(threading.Thread):
    """실행 중에만 도는 감시 스레드. 위험하면 on_critical(이유)를 부른다."""

    def __init__(self, cfg: dict, log: Callable[..., object], captures: Callable[[], int],
                 on_critical: Callable[[str], None]):
        super().__init__(name="health", daemon=True)
        self.cfg, self.log, self.captures, self.on_critical = cfg, log, captures, on_critical
        self._stop_event = threading.Event()
        self.latest: Snapshot | None = None
        self.start_ld: float | None = None
        self.start_time = time.monotonic()
        self._warned_at = 0.0

    def stop(self):
        self._stop_event.set()

    @property
    def settings(self) -> dict:
        return self.cfg["general"].get("memory", {})

    def growth_per_hour(self) -> float | None:
        if self.latest is None or self.latest.ldplayer_mb is None or self.start_ld is None:
            return None
        hours = (time.monotonic() - self.start_time) / 3600
        return (self.latest.ldplayer_mb - self.start_ld) / hours if hours >= 0.05 else None

    def run(self):
        snap = take_snapshot()
        if snap is None:
            self.log("psutil이 없어 메모리 감시를 끕니다. pip install psutil", problem=True)
            return
        while not self._stop_event.is_set():
            snap = take_snapshot(self.captures())
            self.latest = snap
            if self.start_ld is None and snap.ldplayer_mb is not None:
                self.start_ld = snap.ldplayer_mb
            try:
                append_rotated(LOG_DIR / "memory.jsonl", json.dumps(asdict(snap), ensure_ascii=False))
            except OSError:
                pass
            self._check(snap)
            self._stop_event.wait(max(10, int(self.settings.get("interval_sec", 60))))

    def _check(self, snap: Snapshot):
        s = self.settings
        stop_mb = float(s.get("stop_available_mb", 500))
        warn_mb = float(s.get("warn_available_mb", 1000))
        ld_warn = float(s.get("ldplayer_warn_mb", 4096))
        ld_text = f"LD플레이어 {snap.ldplayer_mb:.0f}MB, " if snap.ldplayer_mb is not None else ""
        if snap.available_mb < stop_mb:
            self.on_critical(f"남은 메모리가 {snap.available_mb:.0f}MB로 기준 {stop_mb:.0f}MB보다 적습니다 "
                             f"({ld_text}시스템 사용 {snap.system_percent:.0f}%)")
            return
        now = time.monotonic()
        if now - self._warned_at < 600:   # 경고는 10분에 한 번
            return
        if snap.available_mb < warn_mb:
            self._warned_at = now
            self.log(f"남은 메모리가 {snap.available_mb:.0f}MB입니다 ({ld_text}시스템 사용 "
                     f"{snap.system_percent:.0f}%). 다른 프로그램을 닫거나 LD플레이어 재시작을 권합니다.",
                     problem=True)
        elif snap.ldplayer_mb is not None and snap.ldplayer_mb > ld_warn:
            self._warned_at = now
            self.log(f"LD플레이어 메모리가 {snap.ldplayer_mb:.0f}MB로 기준 {ld_warn:.0f}MB를 넘었습니다. "
                     "계속 늘어나면 LD플레이어 재시작을 권합니다.", problem=True)
