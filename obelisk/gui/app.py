"""통합 GUI 창."""
import queue
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from .. import __version__, config
from ..core.health import LOG_DIR, append_rotated
from ..core.logger import LogIdGenerator
from ..core.runner import MacroRunner
from ..core.stats import Stats
from ..setup.game_settings import FIXED, OK, REQUIRED, GameSettingsRunner
from .bombs_tab import BombsTab
from .freebie_tab import FreebieTab
from .home_tab import HomeTab
from .lootbug_tab import LootbugTab
from .setup_tab import SetupTab

MAX_LINES_PER_POLL = 300  # 한 번에 너무 많이 넣어 창이 굳지 않도록


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
        # 다른 스레드(실행기, 설정 확인, F8 단축키)에서 GUI를 바꿀 때는 여기에 넣고
        # GUI 스레드의 _poll에서 실행한다. tkinter는 다른 스레드에서 직접 부르면 멈출 수 있다.
        self.ui_calls: queue.Queue = queue.Queue()
        self.log_ids = LogIdGenerator()

        nb = self.nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=6, pady=6)
        self.home = HomeTab(nb, self.cfg, on_toggle=self.toggle, on_change=self._save,
                            on_reset_stats=self._reset_stats)
        nb.add(self.home, text="Home")
        self.setup = SetupTab(nb, on_check=self.check_game_settings)
        nb.add(self.setup, text="Setup")
        nb.add(LootbugTab(nb, self.cfg, self._save), text="Lootbug")
        nb.add(FreebieTab(nb, self.cfg, self._save), text="Freebie")
        nb.add(BombsTab(nb, self.cfg, self._save), text="Bombs")
        self._show_required_state()

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

    def call_soon(self, fn, *args):
        """어느 스레드에서 불러도 되는, GUI 스레드에서 fn(*args)를 실행 예약."""
        self.ui_calls.put((fn, args))

    def _poll(self):
        while not self.ui_calls.empty():
            fn, args = self.ui_calls.get()
            fn(*args)
        lines = []
        while len(lines) < MAX_LINES_PER_POLL and not self.logq.empty():
            lines.append(self.logq.get())
        if lines:
            self.home.append(lines)
            self._write_logfile(lines)
        if self.runner and not self.runner.is_alive():
            self.runner = None
            self.stats.end_session()
            self.home.set_running(False)
            self.setup.set_busy(False)
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
        if self.setup_runner:
            self.log("게임 설정 확인이 끝난 뒤에 실행해 주세요.")
            return
        if not self._required_verified():
            self.log("[!] 필수 게임 설정이 확인되지 않아 실행하지 않습니다.")
            self.log("    Setup 탭에서 '필수 설정 확인 및 적용'을 누르고, 모든 항목이 "
                     "정상 또는 바꿈으로 끝난 뒤 다시 Run을 눌러 주세요.")
            self.nb.select(self.setup)
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
    def check_game_settings(self, keys: list[str], title: str):
        if self.runner or self.setup_runner:
            return
        self.setup.set_busy(True)
        self.setup_runner = GameSettingsRunner(
            self.cfg, keys, title, self.log, lambda r: self.call_soon(self._settings_done, r))
        self.setup_runner.start()

    def _settings_done(self, results: dict):
        self.setup_runner = None
        self.setup.show_results(results)
        self.setup.set_busy(False)
        self._update_required_state(results)

    # ── 필수 설정 확인 기록 ───────────────────────
    # 필수 설정을 모두 맞춘 기록을 config.json에 남겨 두고 Run 전에 확인한다.
    # 필수 항목이 새로 추가되면 기록에 없는 항목이 생기므로 다시 확인하게 된다.
    def _required_verified(self) -> bool:
        done = set(self.cfg["general"].get("required_verified", []))
        return all(s.key in done for s in REQUIRED)

    def _update_required_state(self, results: dict):
        req = [s.key for s in REQUIRED]
        if not any(k in results for k in req):
            return  # 추천 설정만 확인한 경우
        general = self.cfg["general"]
        if all(results.get(k) in (OK, FIXED) for k in req):
            general["required_verified"] = req
            general["required_verified_at"] = datetime.now().isoformat(timespec="seconds")
            self.log("필수 설정 확인 완료. 이제 Run으로 실행할 수 있습니다.")
        else:
            general["required_verified"] = []
            general.pop("required_verified_at", None)
            bad = [s.label for s in REQUIRED if results.get(s.key) not in (OK, FIXED)]
            self.log("[!] 필수 설정 중 맞추지 못한 항목이 있어 Run을 쓸 수 없습니다: " + ", ".join(bad))
            self.log("    게임에서 직접 맞춘 뒤 '필수 설정 확인 및 적용'을 다시 눌러 주세요.")
        self._save()
        self._show_required_state()

    def _show_required_state(self):
        at = self.cfg["general"].get("required_verified_at")
        if self._required_verified() and at:
            t = datetime.fromisoformat(at)
            self.setup.set_required_state(f"확인됨 ({t:%m-%d %H:%M})", ok=True)
        else:
            self.setup.set_required_state("확인 필요 (확인 전에는 Run이 실행되지 않음)", ok=False)

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
            keyboard.add_hotkey("f8", lambda: self.call_soon(self.stop))
            self.log("F8을 누르면 언제든 정지합니다.")
        except Exception:
            self.bind_all("<F8>", lambda e: self.stop())
            self.log("keyboard 패키지가 없어 F8은 이 창이 활성일 때만 동작합니다.")

    def _write_logfile(self, lines: list[str]):
        try:
            append_rotated(LOG_DIR / "macro.log", "\n".join(lines))
        except OSError:
            pass

    def _save(self):
        config.save(self.cfg)

    def _on_close(self):
        self.stop()
        self._save()
        self.stats.save(force=True)
        try:
            import keyboard
            keyboard.unhook_all()
        except Exception:
            pass
        self.destroy()
