"""Home 탭: 왼쪽 로그, 오른쪽 옵션·상태·수치, 오른쪽 아래 실행 버튼."""
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from .stats_panel import StatsPanel

MAX_LOG_LINES = 2000


class HomeTab(ttk.Frame):
    def __init__(self, master, cfg: dict, on_toggle, on_change, on_reset_stats):
        super().__init__(master, padding=8)
        self.general = cfg["general"]
        self.on_change = on_change
        self.columnconfigure(0, weight=3)
        self.columnconfigure(1, weight=2)
        self.rowconfigure(0, weight=1)

        log_frame = ttk.LabelFrame(self, text="Log", padding=4)
        log_frame.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 8))
        self.logbox = ScrolledText(log_frame, state="disabled", wrap="word",
                                   font=("Consolas", 9), width=60)
        self.logbox.pack(fill="both", expand=True)

        side = ttk.Frame(self)
        side.grid(row=0, column=1, sticky="nsew")

        opts = ttk.LabelFrame(side, text="Options", padding=6)
        opts.pack(fill="x")
        self.debug = tk.BooleanVar(value=self.general.get("debug", False))
        ttk.Checkbutton(opts, text="Debug", variable=self.debug,
                        command=self._apply).pack(anchor="w")
        ttk.Label(opts, text="문제가 생긴 작업의 화면만 debug/로그ID.png로 저장",
                  foreground="#555").pack(anchor="w")
        self.stream = tk.BooleanVar(value=self.general.get("capture") == "stream")
        ttk.Checkbutton(opts, text="연속 캡처(영상)", variable=self.stream,
                        command=self._apply).pack(anchor="w", pady=(6, 0))
        ttk.Label(opts, text="screenrecord로 화면을 받아 LD플레이어 메모리 증가를 줄임.\n"
                             "다음 Run부터 적용, 안 되면 일반 캡처로 자동 전환",
                  foreground="#555", justify="left").pack(anchor="w")

        self.stats = StatsPanel(side)
        self.stats.pack(fill="both", expand=True, pady=(8, 0))

        bottom = ttk.Frame(self)
        bottom.grid(row=1, column=1, sticky="ew", pady=(8, 0))
        ttk.Button(bottom, text="누적 초기화", command=on_reset_stats).pack(side="left")
        self.run_btn = ttk.Button(bottom, text="Run", width=14, command=on_toggle)
        self.run_btn.pack(side="right")

    def _apply(self):
        self.general["debug"] = bool(self.debug.get())
        self.general["capture"] = "stream" if self.stream.get() else "raw"
        self.on_change()

    def append(self, lines: list[str]):
        """여러 줄을 한 번에 넣는다 (위젯 갱신을 한 번으로 줄임)."""
        if not lines:
            return
        box = self.logbox
        box.configure(state="normal")
        box.insert("end", "\n".join(lines) + "\n")
        extra = int(box.index("end-1c").split(".")[0]) - MAX_LOG_LINES
        if extra > 0:
            box.delete("1.0", f"{extra + 1}.0")
        box.see("end")
        box.configure(state="disabled")

    def set_running(self, running: bool):
        self.run_btn.configure(text="Stop" if running else "Run")
