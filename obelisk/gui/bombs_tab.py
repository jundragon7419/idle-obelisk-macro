"""Bombs 탭: 사용 여부, 터뜨리는 순서, 주기, 폭탄 사이 간격.

바꾼 값은 바로 설정에 반영되고 저장된다. 실행 중에도 다음 주기부터 적용된다.
"""
import tkinter as tk
from tkinter import ttk

from ..features.bombs.vision import BOMB_NAMES, ORDERS


def _order_text(key: str) -> str:
    return " → ".join(BOMB_NAMES[k].replace(" Bomb", "") for k in ORDERS[key])


class BombsTab(ttk.Frame):
    def __init__(self, master, cfg: dict, on_change):
        super().__init__(master, padding=10)
        self.cfg = cfg["bombs"]
        self.on_change = on_change

        self.enabled = tk.BooleanVar(value=self.cfg.get("enabled", False))
        ttk.Checkbutton(self, text="폭탄 자동 터뜨리기 사용", variable=self.enabled,
                        command=self._apply).pack(anchor="w")
        ttk.Label(self, text="정한 주기마다 오른쪽 아래 폭탄 가방을 열고, 윗줄 왼쪽 4칸(Gem, Cherry, "
                             "Battery, D20)을 고른 순서대로 눌러 Fire All로 터뜨린 뒤 가방을 닫습니다. "
                             "발사 방식이 토끼(Fire)나 거북(Fire Slow)이면 핵폭발(Fire All)로 바꿉니다.",
                  wraplength=560, foreground="#555", justify="left").pack(anchor="w", pady=(4, 0))

        order = ttk.LabelFrame(self, text="터뜨리는 순서", padding=8)
        order.pack(fill="x", pady=(10, 0))
        self.order = tk.StringVar(value=self.cfg.get("order", "cherry_first"))
        for key in ORDERS:
            ttk.Radiobutton(order, text=_order_text(key), value=key, variable=self.order,
                            command=self._apply).pack(anchor="w")

        opts = ttk.LabelFrame(self, text="실행 옵션", padding=8)
        opts.pack(fill="x", pady=(10, 0))
        ttk.Label(opts, text="주기(초)").grid(row=0, column=0, sticky="w")
        self.interval = tk.IntVar(value=int(self.cfg.get("check_interval_sec", 60)))
        self._spin(opts, self.interval, 10, 86400).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(opts, text="폭탄 사이 간격(초)").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.delay = tk.DoubleVar(value=float(self.cfg.get("delay_sec", 1.0)))
        self._spin(opts, self.delay, 0, 30, inc=0.5).grid(row=1, column=1, sticky="w", padx=6,
                                                          pady=(6, 0))
        ttk.Label(opts, text="Fire All 확인 창은 Setup 탭의 필수 설정(Disable Confirmation on Fire "
                             "All Bombs)으로 꺼 둡니다.", foreground="#555", wraplength=520,
                  justify="left").grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

    def _spin(self, parent, var, lo, hi, inc=1):
        sp = ttk.Spinbox(parent, from_=lo, to=hi, increment=inc, width=7, textvariable=var,
                         command=self._apply)
        sp.bind("<FocusOut>", lambda e: self._apply())
        sp.bind("<Return>", lambda e: self._apply())
        return sp

    def _read(self, var, key, lo, default, cast):
        try:
            v = max(lo, cast(var.get()))
        except (tk.TclError, ValueError):
            v = cast(self.cfg.get(key, default))
        var.set(v)
        return v

    def _apply(self):
        self.cfg["enabled"] = bool(self.enabled.get())
        self.cfg["order"] = self.order.get() if self.order.get() in ORDERS else "cherry_first"
        self.cfg["check_interval_sec"] = self._read(self.interval, "check_interval_sec", 10, 60, int)
        self.cfg["delay_sec"] = self._read(self.delay, "delay_sec", 0, 1.0, float)
        self.on_change()
