"""통합 GUI 창."""
import queue
import tkinter as tk
from tkinter import messagebox, ttk

from .. import __version__, config
from ..core.logger import LogIdGenerator
from ..core.runner import MacroRunner
from ..core.stats import Stats
from ..setup.game_settings import GameSettingsRunner
from .freebie_tab import FreebieTab
from .home_tab import HomeTab
from .lootbug_tab import LootbugTab
from .setup_tab import SetupTab


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Idle Obelisk Macro v{__version__}")
        self.geometry("920x680")
        self.minsize(760, 480)

        self.cfg = config.load()
        self.runner: MacroRunner | None = None
        self.setup_runner: GameSettingsRunner | None = None
        self.stats = Stats()
        self.logq: queue.Queue[str] = queue.Queue()
        self.log_ids = LogIdGenerator()

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=6, pady=6)
        self.home = HomeTab(nb, self.cfg, on_toggle=self.toggle, on_change=self._save,
                            on_reset_stats=self._reset_stats)
        nb.add(self.home, text="Home")
        self.setup = SetupTab(nb, on_check=self.check_game_settings)
        nb.add(self.setup, text="Setup")
        nb.add(LootbugTab(nb, self.cfg, self._save), text="Lootbug")
        nb.add(FreebieTab(nb, self.cfg, self._save), text="Freebie")

        self._setup_hotkey()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(150, self._poll)
        self.after(500, self._refresh_stats)

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
            self.stats.end_session()
            self.home.set_running(False)
            self.setup.set_busy(False)
        self.after(150, self._poll)
        self.after(500, self._refresh_stats)

    # ── 실행/정지 ────────────────────────────────
    def toggle(self):
        if self.runner:
            self.stop()
        else:
            self.start()

    def start(self):
        if self.runner:
            return
        if self.setup_runner:
            self.log("게임 설정 확인이 끝난 뒤에 실행해 주세요.")
            return
        self._save()
        self.stats.start_session()
        self.runner = MacroRunner(self.cfg, self.log, self.stats)
        self.runner.start()
        self.home.set_running(True)
        self.setup.set_busy(False, macro_running=True)
        self.log("실행 시작")

    def stop(self):
        if self.runner:
            self.runner.stop()
            self.log("정지 요청")

    # ── 게임 설정 확인 ────────────────────────────
    def check_game_settings(self):
        if self.runner or self.setup_runner:
            return
        self.setup.set_busy(True)
        self.setup_runner = GameSettingsRunner(
            self.cfg, self.log, lambda r: self.after(0, self._settings_done, r))
        self.setup_runner.start()

    def _settings_done(self, results: dict):
        self.setup_runner = None
        self.setup.show_results(results)
        self.setup.set_busy(False)

    # ── 수치 ─────────────────────────────────────
    def _refresh_stats(self):
        if self.runner:
            state = "실행 중"
        elif self.setup_runner:
            state = "설정 확인 중"
        else:
            state = "정지"
        self.home.stats.refresh(self.stats, self.runner, self.cfg, state)
        self.stats.save()
        self.after(1000, self._refresh_stats)

    def _reset_stats(self):
        if messagebox.askyesno("누적 초기화", "누적 수치를 모두 지울까요? 이번 실행 수치는 그대로 둡니다."):
            self.stats.reset_total()
            self.log("누적 수치를 초기화했습니다.")

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
        self.stats.save(force=True)
        self.destroy()
