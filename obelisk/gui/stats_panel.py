"""Home 탭 오른쪽 수치 표시 (이번 실행 / 누적)."""
import time
import tkinter as tk
from datetime import datetime
from tkinter import ttk

from ..core.stats import Stats
from ..features.bombs.vision import BOMB_NAMES
from ..features.lootbug.vision import BUFF_NAMES

LOOTBUG_FAILS = [("popup", "팝업 안 열림"), ("toggle", "체크 반영 안 됨"),
                 ("held", "구매 보류"), ("buy", "구매 안 됨")]
BOMBS_FAILS = [("bag", "가방 안 열림"), ("slots", "칸 확인 실패"), ("select", "선택 실패"),
               ("mode", "Fire All 전환 실패"), ("close", "가방 안 닫힘")]
FREEBIE_FAILS = [("shop", "상점 진입 실패"), ("not_found", "Pack 못 찾음"),
                 ("claim", "Claim 실패"), ("count", "개수 읽기 실패")]


def _fmt_duration(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def _fmt_time(iso: str | None) -> str:
    if not iso:
        return "-"
    t = datetime.fromisoformat(iso)
    return t.strftime("%H:%M:%S") if t.date() == datetime.now().date() else t.strftime("%m-%d %H:%M")


class StatsPanel(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        st = ttk.LabelFrame(self, text="Status", padding=6)
        st.pack(fill="x")
        self.status_vars = {}
        for i, (key, label) in enumerate([("state", "상태"), ("elapsed", "실행 시간"), ("device", "기기"),
                                          ("capture", "캡처"), ("memory", "메모리")]):
            ttk.Label(st, text=label).grid(row=i, column=0, sticky="w")
            var = tk.StringVar(value="-")
            ttk.Label(st, textvariable=var).grid(row=i, column=1, sticky="w", padx=(10, 0))
            self.status_vars[key] = var

        frame = ttk.LabelFrame(self, text="Stats", padding=4)
        frame.pack(fill="both", expand=True, pady=(8, 0))
        self.tree = ttk.Treeview(frame, columns=("session", "total"), height=10)
        self.tree.heading("#0", text="항목")
        self.tree.heading("session", text="이번 실행")
        self.tree.heading("total", text="누적")
        self.tree.column("#0", width=170, stretch=True)
        self.tree.column("session", width=70, anchor="e", stretch=False)
        self.tree.column("total", width=70, anchor="e", stretch=False)
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.tag_configure("section", font=("", 9, "bold"))
        self._items: dict[str, list[str]] = {}   # 섹션별 행 iid (값만 바꿔 다시 그리지 않음)
        self._last: dict[str, tuple] = {}

    def _rows(self, stats: Stats, runner, cfg, key) -> list[tuple[str, str, str]]:
        g = lambda scope, k: stats.get(scope, f"{key}.{k}", 0)
        rows = []
        if key == "lootbug":
            rows.append(("수령 횟수", g("session", "looted"), g("total", "looted")))
            for b in stats.keys_under("lootbug.buffs"):
                rows.append((f"구매: {BUFF_NAMES.get(b, b)}", g("session", f"buffs.{b}"),
                             g("total", f"buffs.{b}")))
            fails = LOOTBUG_FAILS
        elif key == "bombs":
            rows.append(("한 바퀴 횟수", g("session", "rounds"), g("total", "rounds")))
            for b, name in BOMB_NAMES.items():
                rows.append((f"발사: {name}", g("session", f"fired.{b}"), g("total", f"fired.{b}")))
            fails = BOMBS_FAILS
        else:
            rows.append(("받은 프리비", g("session", "claimed"), g("total", "claimed")))
            fails = FREEBIE_FAILS
        for k, label in fails:
            rows.append((f"실패: {label}", g("session", f"fail.{k}"), g("total", f"fail.{k}")))
        rows.append(("마지막 실행" if key == "bombs" else "마지막 수령", _fmt_time(stats.get("total", f"{key}.last_at", None)), ""))
        rows.append(("다음 확인", self._next_check(runner, cfg, key), ""))
        return [(a, str(b), str(c)) for a, b, c in rows]

    @staticmethod
    def _next_check(runner, cfg, key) -> str:
        if not cfg[key].get("enabled"):
            return "꺼짐"
        if runner is None or not runner.is_alive():
            return "-"
        if runner.current == key:
            return "진행 중"
        due = runner.next_due.get(key)
        if due is None:
            return "-"
        return f"{max(0, int(due - time.monotonic()))}초"

    def refresh(self, stats: Stats, runner, cfg, state: str):
        elapsed = stats.elapsed()
        self.status_vars["state"].set(state)
        self.status_vars["elapsed"].set(_fmt_duration(elapsed) if elapsed is not None else "-")
        serial = getattr(getattr(runner, "adb", None), "serial", None) if runner else None
        self.status_vars["device"].set(serial or "-")
        self.status_vars["capture"].set(self._capture_text(runner))
        self.status_vars["memory"].set(self._memory_text(runner))

        # 바뀐 행만 고친다. 행 개수가 달라질 때(새 버프 구매)만 그 섹션을 다시 만든다.
        for key, title in (("lootbug", "Lootbug"), ("freebie", "Freebie"), ("bombs", "Bombs")):
            if not self.tree.exists(key):
                self.tree.insert("", "end", iid=key, text=title, open=True, tags=("section",))
            rows = self._rows(stats, runner, cfg, key)
            items = self._items.get(key, [])
            if len(items) != len(rows):
                for iid in items:
                    self.tree.delete(iid)
                items = [self.tree.insert(key, "end", text=r[0], values=r[1:]) for r in rows]
                self._items[key] = items
            for iid, row in zip(items, rows):
                if self._last.get(iid) != row:
                    self.tree.item(iid, text=row[0], values=row[1:])
                    self._last[iid] = row

    @staticmethod
    def _capture_text(runner) -> str:
        adb = getattr(runner, "adb", None) if runner and runner.is_alive() else None
        if adb is None:
            return "-"
        stream = getattr(adb, "stream", None)
        mode = "연속(영상)" if stream is not None and stream.alive else adb.capture_mode
        return f"{mode} · {adb.capture_count}회"

    @staticmethod
    def _memory_text(runner) -> str:
        health = getattr(runner, "health", None) if runner and runner.is_alive() else None
        snap = getattr(health, "latest", None)
        if snap is None:
            return "-"
        parts = [f"매크로 {snap.macro_mb:.0f}MB"]
        if snap.ldplayer_mb is not None:
            g = health.growth_per_hour()
            parts.append(f"LD {snap.ldplayer_mb:.0f}MB" + (f"({g:+.0f}/h)" if g is not None else ""))
        parts.append(f"여유 {snap.available_mb / 1024:.1f}GB")
        return " · ".join(parts)
