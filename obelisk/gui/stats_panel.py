"""Home 탭 오른쪽 수치 표시 (이번 실행 / 누적)."""
import time
import tkinter as tk
from datetime import datetime
from tkinter import ttk

from ..core.stats import Stats
from ..features.lootbug.vision import BUFF_NAMES

LOOTBUG_FAILS = [("popup", "팝업 안 열림"), ("toggle", "체크 반영 안 됨"),
                 ("held", "구매 보류"), ("buy", "구매 안 됨")]
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
        for i, (key, label) in enumerate([("state", "상태"), ("elapsed", "실행 시간"), ("device", "기기")]):
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
        self._open = {"lootbug": True, "freebie": True}

    def _rows(self, stats: Stats, runner, cfg, key) -> list[tuple[str, str, str]]:
        g = lambda scope, k: stats.get(scope, f"{key}.{k}", 0)
        rows = []
        if key == "lootbug":
            rows.append(("수령 횟수", g("session", "looted"), g("total", "looted")))
            for b in stats.keys_under("lootbug.buffs"):
                rows.append((f"구매: {BUFF_NAMES.get(b, b)}", g("session", f"buffs.{b}"),
                             g("total", f"buffs.{b}")))
            fails = LOOTBUG_FAILS
        else:
            rows.append(("받은 프리비", g("session", "claimed"), g("total", "claimed")))
            fails = FREEBIE_FAILS
        for k, label in fails:
            rows.append((f"실패: {label}", g("session", f"fail.{k}"), g("total", f"fail.{k}")))
        rows.append(("마지막 수령", _fmt_time(stats.get("total", f"{key}.last_at", None)), ""))
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

        # 펼침 상태와 스크롤 위치를 유지하며 다시 그림
        top = self.tree.yview()[0]
        for iid in self.tree.get_children():
            self._open[iid] = bool(self.tree.item(iid, "open"))
            self.tree.delete(iid)
        for key, title in (("lootbug", "Lootbug"), ("freebie", "Freebie")):
            self.tree.insert("", "end", iid=key, text=title, open=self._open.get(key, True),
                             tags=("section",))
            for label, a, b in self._rows(stats, runner, cfg, key):
                self.tree.insert(key, "end", text=label, values=(a, b))
        self.tree.yview_moveto(top)
