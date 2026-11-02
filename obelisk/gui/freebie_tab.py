"""Freebie 탭: 사용 여부, 수령 기준, 확인 주기, 감지만 실행.

바꾼 값은 바로 설정에 반영되고 저장된다. 실행 중에도 다음 주기부터 적용된다.
"""
import tkinter as tk
from tkinter import ttk


class FreebieTab(ttk.Frame):
    def __init__(self, master, cfg: dict, on_change):
        super().__init__(master, padding=10)
        self.cfg = cfg["freebie"]
        self.on_change = on_change

        self.enabled = tk.BooleanVar(value=self.cfg.get("enabled", False))
        ttk.Checkbutton(self, text="프리비 팩 자동 수령 사용", variable=self.enabled,
                        command=self._apply).pack(anchor="w")
        ttk.Label(self, text="홈 화면 오른쪽 아래 상점 버튼에 초록 막대가 차오르면 상점에 들어가 "
                             "Freebie Pack을 찾아 Claim을 누르고 나옵니다.",
                  wraplength=560, foreground="#555").pack(anchor="w", pady=(4, 0))

        opts = ttk.LabelFrame(self, text="실행 옵션", padding=8)
        opts.pack(fill="x", pady=(10, 0))

        ttk.Label(opts, text="확인 주기(초)").grid(row=0, column=0, sticky="w")
        self.interval = tk.IntVar(value=int(self.cfg.get("check_interval_sec", 60)))
        self._spin(opts, self.interval, 10, 3600).grid(row=0, column=1, sticky="w", padx=6)

        ttk.Label(opts, text="수령 기준: 초록 막대 높이(px)").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.level = tk.IntVar(value=int(self.cfg.get("min_level_px", 1)))
        self._spin(opts, self.level, 1, 40).grid(row=1, column=1, sticky="w", padx=6, pady=(6, 0))
        ttk.Label(opts, text="1이면 하나라도 쌓이면 받음. 막대는 쌓인 비율(N/최대)만큼 차오릅니다.",
                  foreground="#555").grid(row=2, column=0, columnspan=2, sticky="w")

        self.detect_only = tk.BooleanVar(value=self.cfg.get("detect_only", False))
        ttk.Checkbutton(opts, text="감지만 실행 (상점에 들어가지 않고 로그만 남김)",
                        variable=self.detect_only, command=self._apply).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))

    def _spin(self, parent, var, lo, hi):
        sp = ttk.Spinbox(parent, from_=lo, to=hi, width=6, textvariable=var, command=self._apply)
        sp.bind("<FocusOut>", lambda e: self._apply())
        sp.bind("<Return>", lambda e: self._apply())
        return sp

    def _read_int(self, var, key, lo, default):
        try:
            v = max(lo, int(var.get()))
        except (tk.TclError, ValueError):
            v = int(self.cfg.get(key, default))
        var.set(v)
        return v

    def _apply(self):
        self.cfg["enabled"] = bool(self.enabled.get())
        self.cfg["check_interval_sec"] = self._read_int(self.interval, "check_interval_sec", 10, 60)
        self.cfg["min_level_px"] = self._read_int(self.level, "min_level_px", 1, 1)
        self.cfg["detect_only"] = bool(self.detect_only.get())
        self.on_change()
