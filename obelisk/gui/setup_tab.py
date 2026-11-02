"""Setup 탭: 매크로에 필요한 게임 설정을 확인하고 맞춘다."""
import tkinter as tk
from tkinter import ttk

from ..setup.game_settings import FAILED, FIXED, MISSING, OK, SETTINGS

STATUS_TEXT = {
    None: ("확인 전", "#777"),
    OK: ("정상", "#1a7f37"),
    FIXED: ("바꿈", "#1a7f37"),
    FAILED: ("바꾸지 못함", "#c62828"),
    MISSING: ("찾지 못함", "#c62828"),
}


class SetupTab(ttk.Frame):
    def __init__(self, master, on_check):
        super().__init__(master, padding=10)
        ttk.Label(self, text="게임 Options → Gameplay → Lootbugs & Freebies 설정이 아래와 같아야 "
                             "매크로가 동작합니다. 버튼을 누르면 게임에서 설정 화면을 열어 확인하고, "
                             "다른 항목은 바꾼 뒤 홈 화면으로 돌아옵니다.",
                  wraplength=600, foreground="#555").pack(anchor="w")

        box = ttk.LabelFrame(self, text="Lootbugs & Freebies", padding=8)
        box.pack(fill="x", pady=(10, 0))
        ttk.Label(box, text="항목", font=("", 9, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(box, text="필요", font=("", 9, "bold")).grid(row=0, column=1, padx=16)
        ttk.Label(box, text="결과", font=("", 9, "bold")).grid(row=0, column=2, sticky="w")
        self.status = {}
        for i, s in enumerate(SETTINGS, start=1):
            ttk.Label(box, text=s.label).grid(row=i, column=0, sticky="w", pady=2)
            ttk.Label(box, text="체크" if s.required else "해제").grid(row=i, column=1, padx=16)
            lbl = tk.Label(box, text="", anchor="w")
            lbl.grid(row=i, column=2, sticky="w")
            self.status[s.key] = lbl
        box.columnconfigure(0, weight=1)
        self.show_results({})

        self.btn = ttk.Button(self, text="게임 설정 확인 및 적용", command=on_check)
        self.btn.pack(anchor="e", pady=(10, 0))
        self.note = ttk.Label(self, text="", foreground="#555")
        self.note.pack(anchor="e")

    def show_results(self, results: dict):
        for key, lbl in self.status.items():
            text, color = STATUS_TEXT[results.get(key)]
            lbl.configure(text=text, fg=color)

    def set_busy(self, busy: bool, macro_running: bool = False):
        if busy:
            self.btn.state(["disabled"])
            self.note.configure(text="확인 중입니다...")
        elif macro_running:
            self.btn.state(["disabled"])
            self.note.configure(text="매크로 실행 중에는 쓸 수 없습니다. Home에서 Stop 후 사용하세요.")
        else:
            self.btn.state(["!disabled"])
            self.note.configure(text="")
