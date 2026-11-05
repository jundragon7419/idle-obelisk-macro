"""Setup 탭: 게임 설정 확인 및 적용.

필수 설정: 매크로가 동작하는 데 필요한 설정.
추천 설정: 데미지 숫자와 효과를 줄여 화면을 잘 보이게 하는 설정. 묶음별로 또는 한 번에 적용.
"""
import tkinter as tk
from tkinter import ttk

from ..setup.game_settings import FAILED, FIXED, MISSING, OK, RECOMMENDED, REQUIRED, groups

STATUS_TEXT = {
    None: ("확인 전", "#777"),
    OK: ("정상", "#1a7f37"),
    FIXED: ("바꿈", "#1a7f37"),
    FAILED: ("바꾸지 못함", "#c62828"),
    MISSING: ("찾지 못함", "#c62828"),
}


class _Scrollable(ttk.Frame):
    """세로 스크롤되는 영역. 내용은 .body에 넣는다."""

    def __init__(self, master):
        super().__init__(master)
        canvas = tk.Canvas(self, highlightthickness=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.body = ttk.Frame(canvas)
        self.body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        win = canvas.create_window((0, 0), window=self.body, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        # 마우스 휠 (Windows)
        canvas.bind("<Enter>", lambda e: canvas.bind_all(
            "<MouseWheel>", lambda ev: canvas.yview_scroll(int(-ev.delta / 120), "units")))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))


class SetupTab(ttk.Frame):
    def __init__(self, master, on_check):
        """on_check(keys, title): 해당 설정들을 게임에서 확인하고 맞춘다."""
        super().__init__(master, padding=(10, 10, 0, 10))
        self.on_check = on_check
        self.status: dict[str, tk.Label] = {}
        self.buttons: list[ttk.Button] = []

        top = ttk.Frame(self)
        top.pack(fill="x", padx=(0, 10))
        ttk.Label(top, text="버튼을 누르면 게임에서 Options 화면을 열어 각 항목을 확인하고, "
                            "다른 항목만 바꾼 뒤 홈 화면으로 돌아옵니다. 매크로 실행 중에는 쓸 수 없습니다.",
                  wraplength=640, foreground="#555").pack(anchor="w")
        self.note = ttk.Label(top, text="", foreground="#555")
        self.note.pack(anchor="w")

        area = _Scrollable(self)
        area.pack(fill="both", expand=True, pady=(6, 0))
        body = area.body

        # ── 필수 ──
        req = ttk.LabelFrame(body, text="필수 설정 (매크로 동작에 필요)", padding=8)
        req.pack(fill="x", padx=(0, 10))
        self._add_groups(req, REQUIRED, per_group_button=False)
        bar = ttk.Frame(req)
        bar.pack(fill="x", pady=(6, 0))
        self.required_state = tk.Label(bar, text="", anchor="w")
        self.required_state.pack(side="left")
        self._button(bar, "필수 설정 확인 및 적용",
                     [s.key for s in REQUIRED], "필수 설정").pack(side="right")

        # ── 추천 ──
        rec = ttk.LabelFrame(body, text="추천 설정 (데미지 숫자와 효과를 줄여 화면을 잘 보이게 함)",
                             padding=8)
        rec.pack(fill="x", padx=(0, 10), pady=(10, 0))
        self._add_groups(rec, RECOMMENDED, per_group_button=True)
        self._button(rec, "추천 설정 전체 적용",
                     [s.key for s in RECOMMENDED], "추천 설정 전체").pack(anchor="e", pady=(6, 0))

        self.show_results({})

    def _button(self, parent, text, keys, title):
        b = ttk.Button(parent, text=text, command=lambda: self.on_check(keys, title))
        self.buttons.append(b)
        return b

    def _add_groups(self, parent, settings, per_group_button: bool):
        for title, items in groups(settings):
            head = ttk.Frame(parent)
            head.pack(fill="x", pady=(6, 2))
            ttk.Label(head, text=title, font=("", 9, "bold")).pack(side="left")
            if per_group_button:
                self._button(head, "적용", [s.key for s in items], title).pack(side="right")
            grid = ttk.Frame(parent)
            grid.pack(fill="x", padx=(12, 0))
            grid.columnconfigure(0, weight=1)
            for i, s in enumerate(items):
                ttk.Label(grid, text=s.label).grid(row=i, column=0, sticky="w", pady=1)
                ttk.Label(grid, text=s.want_text, width=11).grid(row=i, column=1, padx=8)
                lbl = tk.Label(grid, text="", anchor="w", width=10)
                lbl.grid(row=i, column=2, sticky="w")
                self.status[s.key] = lbl

    def set_required_state(self, text: str, ok: bool):
        self.required_state.configure(text=text, fg="#1a7f37" if ok else "#c62828")

    def show_results(self, results: dict):
        """확인한 항목만 결과를 바꾼다 (다른 묶음 결과는 유지)."""
        for key, lbl in self.status.items():
            if key in results or not lbl.cget("text"):
                text, color = STATUS_TEXT[results.get(key)]
                lbl.configure(text=text, fg=color)

    def set_busy(self, busy: bool, macro_running: bool = False):
        disabled = busy or macro_running
        for b in self.buttons:
            b.state(["disabled"] if disabled else ["!disabled"])
        if busy:
            self.note.configure(text="확인 중입니다...")
        elif macro_running:
            self.note.configure(text="매크로 실행 중에는 쓸 수 없습니다. Home에서 Stop 후 사용하세요.")
        else:
            self.note.configure(text="")
