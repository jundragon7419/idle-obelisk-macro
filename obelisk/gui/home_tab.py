"""Home 탭: 왼쪽 로그, 오른쪽 옵션과 요약 영역(추후), 오른쪽 아래 실행 버튼."""
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

MAX_LOG_LINES = 2000


class HomeTab(ttk.Frame):
    def __init__(self, master, cfg: dict, on_toggle, on_change):
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
        ttk.Label(opts, text="로그 한 줄마다 그 순간 화면을 debug 폴더에 "
                             "'로그ID.png'로 저장합니다.",
                  wraplength=200, foreground="#555").pack(anchor="w", pady=(2, 0))

        # 수치 요약은 다음 단계에서 채울 자리
        self.summary = ttk.Frame(side)
        self.summary.pack(fill="both", expand=True, pady=(8, 0))

        self.run_btn = ttk.Button(self, text="Run", width=14, command=on_toggle)
        self.run_btn.grid(row=1, column=1, sticky="se", pady=(8, 0))

    def _apply(self):
        self.general["debug"] = bool(self.debug.get())
        self.on_change()

    def append(self, line: str):
        box = self.logbox
        box.configure(state="normal")
        box.insert("end", line + "\n")
        extra = int(box.index("end-1c").split(".")[0]) - MAX_LOG_LINES
        if extra > 0:
            box.delete("1.0", f"{extra + 1}.0")
        box.see("end")
        box.configure(state="disabled")

    def set_running(self, running: bool):
        self.run_btn.configure(text="Stop" if running else "Run")
