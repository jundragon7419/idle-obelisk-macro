"""통합 GUI 창."""
import queue
import tkinter as tk
from tkinter import ttk

from .. import __version__, config
from ..core.logger import LogIdGenerator
from ..core.runner import MacroRunner
from .freebie_tab import FreebieTab
from .home_tab import HomeTab
from .lootbug_tab import LootbugTab


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Idle Obelisk Macro v{__version__}")
        self.geometry("780x560")
        self.minsize(640, 420)

        self.cfg = config.load()
        self.runner: MacroRunner | None = None
        self.logq: queue.Queue[str] = queue.Queue()
        self.log_ids = LogIdGenerator()

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=6, pady=6)
        self.home = HomeTab(nb, self.cfg, on_toggle=self.toggle, on_change=self._save)
        nb.add(self.home, text="Home")
        nb.add(LootbugTab(nb, self.cfg, self._save), text="Lootbug")
        nb.add(FreebieTab(nb, self.cfg, self._save), text="Freebie")

        self._setup_hotkey()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(150, self._poll)

    # ── 로그 ─────────────────────────────────────
    def log(self, msg: str) -> str:
        """로그를 남기고 로그 ID(16진수)를 돌려준다. 어느 스레드에서 불러도 된다."""
        log_id, now = self.log_ids.next()
        self.logq.put(f"[{log_id}] {now:%H:%M:%S} {msg}")
        return log_id

    def _poll(self):
        while not self.logq.empty():
            self.home.append(self.logq.get())
        if self.runner and not self.runner.is_alive():
            self.runner = None
            self.home.set_running(False)
        self.after(150, self._poll)

    # ── 실행/정지 ────────────────────────────────
    def toggle(self):
        if self.runner:
            self.stop()
        else:
            self.start()

    def start(self):
        if self.runner:
            return
        self._save()
        self.runner = MacroRunner(self.cfg, self.log)
        self.runner.start()
        self.home.set_running(True)
        self.log("실행 시작")

    def stop(self):
        if self.runner:
            self.runner.stop()
            self.log("정지 요청")

    def _setup_hotkey(self):
        try:
            import keyboard
            keyboard.add_hotkey("f8", lambda: self.after(0, self.stop))
            self.log("F8을 누르면 언제든 정지합니다.")
        except Exception:
            self.bind_all("<F8>", lambda e: self.stop())
            self.log("keyboard 패키지가 없어 F8은 이 창이 활성일 때만 동작합니다.")

    def _save(self):
        config.save(self.cfg)

    def _on_close(self):
        self.stop()
        self._save()
        self.destroy()
