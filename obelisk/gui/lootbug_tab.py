"""Lootbug 탭: 사용 여부, 구매할 버프, 확인 주기, 감지만 실행.

바꾼 값은 바로 설정에 반영되고 저장된다. 실행 중에도 다음 주기부터 적용된다.
"""
import tkinter as tk
from tkinter import ttk

from ..features.lootbug.vision import BUFF_NAMES


class LootbugTab(ttk.Frame):
    def __init__(self, master, cfg: dict, on_change):
        super().__init__(master, padding=10)
        self.cfg = cfg["lootbug"]
        self.on_change = on_change

        self.enabled = tk.BooleanVar(value=self.cfg.get("enabled", True))
        ttk.Checkbutton(self, text="루트버그 자동 수령 사용", variable=self.enabled,
                        command=self._apply).pack(anchor="w")

        buffs = ttk.LabelFrame(self, text="구매할 버프", padding=8)
        buffs.pack(fill="x", pady=(10, 0))
        ttk.Label(buffs, text="팝업에서 여기 체크한 버프만 체크하고 Buy Checked를 누릅니다. "
                              "아무것도 고르지 않으면 루트버그만 수령합니다.",
                  wraplength=560, foreground="#555").grid(row=0, column=0, columnspan=2,
                                                         sticky="w", pady=(0, 6))
        wanted = set(self.cfg.get("wanted_buffs", []))
        self.buff_vars = {}
        for i, (key, label) in enumerate(BUFF_NAMES.items()):
            var = tk.BooleanVar(value=key in wanted)
            ttk.Checkbutton(buffs, text=label, variable=var, command=self._apply).grid(
                row=1 + i // 2, column=i % 2, sticky="w", padx=4, pady=2)
            self.buff_vars[key] = var
        buffs.columnconfigure(0, weight=1)
        buffs.columnconfigure(1, weight=1)

        opts = ttk.LabelFrame(self, text="실행 옵션", padding=8)
        opts.pack(fill="x", pady=(10, 0))
        ttk.Label(opts, text="확인 주기(초)").grid(row=0, column=0, sticky="w")
        self.interval = tk.IntVar(value=int(self.cfg.get("check_interval_sec", 30)))
        spin = ttk.Spinbox(opts, from_=5, to=600, width=6, textvariable=self.interval,
                           command=self._apply)
        spin.grid(row=0, column=1, sticky="w", padx=6)
        spin.bind("<FocusOut>", lambda e: self._apply())
        spin.bind("<Return>", lambda e: self._apply())

        self.detect_only = tk.BooleanVar(value=self.cfg.get("detect_only", False))
        ttk.Checkbutton(opts, text="감지만 실행 (탭하지 않고 debug 폴더에 표시 이미지 저장)",
                        variable=self.detect_only, command=self._apply).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))

    def _apply(self):
        try:
            interval = max(5, int(self.interval.get()))
        except (tk.TclError, ValueError):
            interval = int(self.cfg.get("check_interval_sec", 30))
            self.interval.set(interval)
        self.cfg["enabled"] = bool(self.enabled.get())
        self.cfg["wanted_buffs"] = [k for k, v in self.buff_vars.items() if v.get()]
        self.cfg["check_interval_sec"] = interval
        self.cfg["detect_only"] = bool(self.detect_only.get())
        self.on_change()
