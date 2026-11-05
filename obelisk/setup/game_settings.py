"""게임 설정 확인 및 적용 (Options 화면).

필수 설정은 매크로가 동작하는 데 필요한 것이고, 추천 설정은 데미지 숫자나 효과를
줄여서 화면 인식이 잘 되게 하는 것이다.

흐름: 홈 하단 가운데 메뉴 버튼 → Options → 설정 탭(Gameplay/Menus/Display) 선택 →
목록을 맨 위로 올린 뒤 내려가며 항목 라벨을 찾음 → 다르면 체크박스를 한 번 탭하고
반영 확인 (순환 항목은 원하는 문구가 나올 때까지 탭) → X로 닫고 홈 복귀.
"""
import threading
import time
from dataclasses import dataclass
from typing import Callable

import cv2
import numpy as np

from ..core import screen as scr
from ..core.adb import Adb, AdbError
from ..core.debuglog import DebugLogger
from ..core.imaging import imread
from ..paths import TEMPLATES

MENU_BTN = (360, 1210)             # 홈 하단 가운데 네모 4개 버튼
TAB_Y, TAB_HALF_W = 121, 46
TABS_X = {"All": 99, "General": 203, "Gameplay": 308, "Display": 411, "Offline": 515, "Menus": 619}
TABS_ROI = (52, 100, 668, 143)
LIST_Y = (170, 1000)               # 설정 목록이 보이는 범위 (아래쪽은 Discord 등 버튼 판에 가림)
CHECKBOX_X = 78
LABEL_MIN_SCORE = 0.8              # 다른 항목 라벨과는 0.7 이하
OPTIONS_MIN_SCORE = 0.85
MAX_SCROLLS = 15
MAX_CYCLE_TAPS = 8
CYCLE_WORD_X = (380, 470)          # 순환 항목에서 ':' 바로 뒤 첫 단어가 오는 가로 범위


@dataclass(frozen=True)
class Setting:
    key: str
    tab: str          # 설정 화면 상단 탭
    section: str      # 탭 안의 묶음 제목
    label: str
    want: str         # "check" / "uncheck" / 순환 항목은 원하는 문구 (예: "All of them")

    @property
    def cycle(self) -> bool:
        return self.want not in ("check", "uncheck")

    @property
    def want_text(self) -> str:
        return {"check": "체크", "uncheck": "해제"}.get(self.want, self.want)


def _s(key, tab, section, label, want="check"):
    return Setting(key, tab, section, label, want)


REQUIRED = [
    _s("fire_all_confirm", "Gameplay", "Bombs & Items", "Disable Confirmation on Fire All Bombs"),
    _s("auto_loot_free", "Gameplay", "Lootbugs & Freebies", "Auto-Loot free Lootbug offerings"),
    _s("remove_gem_confirm", "Gameplay", "Lootbugs & Freebies", "Remove Lootbug Gem confirmation", "uncheck"),
    _s("loot_all_banked", "Gameplay", "Lootbugs & Freebies", "Enable Loot-All Banked Lootbugs"),
    _s("tap_any_loot_all", "Gameplay", "Lootbugs & Freebies", "Tap any Lootbug to Loot-All"),
    _s("one_click_freebies", "Gameplay", "Lootbugs & Freebies", "One Click Claim all Banked Freebies"),
]

RECOMMENDED = [
    _s("drones_invisible", "Menus", "Drones", "Make Drones Invisible"),
    _s("stars_invisible", "Menus", "Stargazing", "Make Stars Invisible", "All of them"),
    _s("ore_damage_popups", "Display", "Popups & Tooltips", "Disable Ore Damage Popups"),
    _s("compact_text_popups", "Display", "Popups & Tooltips", "More Compact Text Popups"),
    _s("void_portal_popups", "Display", "Popups & Tooltips", "Hide Void Portal Resource Gain Popups"),
    _s("coal_full_popup", "Display", "Popups & Tooltips", "Hide Coal Full Popup"),
    _s("consistent_ore", "Display", "Graphics", "Consistent Ore Position"),
    _s("minimize_mining_fx", "Display", "Graphics", "Minimize Mining Effects To Stop Flashing"),
    _s("disable_bomb_anim", "Display", "Graphics", "Disable All Bomb Animations"),
    _s("cloud_zone_dim", "Display", "Graphics", "Cloud Zone Brightness Reduction"),
    _s("drone_radius", "Display", "Graphics", "Disable Drone radius display"),
]

ALL_SETTINGS = {s.key: s for s in REQUIRED + RECOMMENDED}

# 결과 코드
OK, FIXED, FAILED, MISSING = "ok", "fixed", "failed", "missing"


def groups(settings: list[Setting]) -> list[tuple[str, list[Setting]]]:
    """'탭 › 묶음' 제목별로 나눈다 (순서 유지)."""
    out: dict[str, list[Setting]] = {}
    for s in settings:
        out.setdefault(f"{s.tab} › {s.section}", []).append(s)
    return list(out.items())


def _gray(img):
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def _ratio(img, roi, lo_h, hi_h):
    x1, y1, x2, y2 = roi
    hsv = cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2HSV)
    m = (hsv[..., 0] >= lo_h) & (hsv[..., 0] <= hi_h) & (hsv[..., 1] > 120) & (hsv[..., 2] > 120)
    return float(m.mean())


def _tab_roi(tab):
    x = TABS_X[tab]
    return (x - TAB_HALF_W, 100, x + TAB_HALF_W, 143)


def is_checked(screen, cy) -> bool:
    """체크박스 안 흰 체크 표시 비율 (체크 0.38~0.39, 빈칸 0.00)."""
    box = screen[cy - 14:cy + 14, CHECKBOX_X - 14:CHECKBOX_X + 14]
    return float((box.min(axis=2) > 200).mean()) > 0.2


class GameSettingsTask:
    def __init__(self, adb, log, sleep):
        self.adb, self.log, self.sleep = adb, log, sleep
        self.options_icon = _gray(imread(TEMPLATES / "ui" / "options_icon.png"))
        self.labels = {k: _gray(imread(TEMPLATES / "ui" / f"setting_{k}.png")) for k in ALL_SETTINGS}
        self.cycle_targets = {s.key: _gray(imread(TEMPLATES / "ui" / f"setting_{s.key}_all.png"))
                              for s in ALL_SETTINGS.values() if s.cycle}

    # ── 화면 판별 ────────────────────────────────
    @staticmethod
    def _match(screen_gray, tpl):
        r = cv2.matchTemplate(screen_gray, tpl, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(r)
        return score, loc

    def _options_open(self, screen) -> bool:
        """설정 화면 상단의 탭 버튼 줄(빨강/초록)이 보이면 설정 화면."""
        return scr.menu_open(screen) and (
            _ratio(screen, TABS_ROI, 0, 8) + _ratio(screen, TABS_ROI, 170, 180)
            + _ratio(screen, TABS_ROI, 40, 85)) > 0.4

    @staticmethod
    def _tab_active(screen, tab) -> bool:
        return _ratio(screen, _tab_roi(tab), 40, 85) > 0.4

    def _wait(self, cond, timeout=3.0):
        deadline = time.monotonic() + timeout
        while True:
            screen = self.adb.screenshot()
            if cond(screen):
                return screen
            if time.monotonic() > deadline:
                return None
            self.sleep(0.4)

    # ── 이동 ─────────────────────────────────────
    def _go_home(self) -> bool:
        for _ in range(4):
            screen = self.adb.screenshot()
            if scr.at_home(screen):
                return True
            if scr.menu_open(screen):
                self.adb.tap(*scr.TOOLBAR_X_BTN)
                self.sleep(0.8)
            else:
                return False
        return scr.at_home(self.adb.screenshot())

    def _open_options(self) -> bool:
        screen = self.adb.screenshot()
        if self._options_open(screen):
            return True
        if not scr.at_home(screen) and not self._go_home():
            self.log("홈 화면으로 돌아오지 못해 설정 화면을 열 수 없습니다.", problem=True)
            return False
        self.adb.tap(*MENU_BTN)
        screen = self._wait(lambda s: self._match(_gray(s), self.options_icon)[0] >= OPTIONS_MIN_SCORE)
        if screen is None:
            self.log("메뉴에서 Options 버튼을 찾지 못했습니다.", problem=True)
            return False
        _, (x, y) = self._match(_gray(screen), self.options_icon)
        h, w = self.options_icon.shape
        self.adb.tap(x + w // 2, y + h // 3)  # 아이콘 부분
        if self._wait(self._options_open) is None:
            self.log("Options 화면이 열리지 않았습니다.", problem=True)
            return False
        return True

    def _open_tab(self, tab) -> bool:
        self.adb.tap(TABS_X[tab], TAB_Y)
        if self._wait(lambda s: self._tab_active(s, tab), timeout=2.0) is None:
            self.log(f"{tab} 탭으로 바뀌지 않았습니다.", problem=True)
            return False
        self.sleep(0.5)
        return True

    # ── 스크롤 ───────────────────────────────────
    @staticmethod
    def _list_strip(screen):
        # 라벨 상자가 있는 가로 범위만 써서 뒤에 비치는 게임 화면의 움직임 영향을 줄임
        return _gray(screen[LIST_Y[0]:LIST_Y[1], 130:650]).astype(np.float32)

    def _scroll(self, down: bool) -> bool:
        """목록을 스크롤한다. 더 움직이지 않으면(끝) False."""
        before = self._list_strip(self.adb.screenshot())
        if down:
            self.adb.swipe(360, 850, 360, 400, 600)
        else:
            self.adb.swipe(360, 300, 360, 900, 400)
        self.sleep(1.0)
        after = self._list_strip(self.adb.screenshot())
        (_, dy), _ = cv2.phaseCorrelate(before, after)
        return abs(dy) >= 3

    def _to_top(self):
        for _ in range(MAX_SCROLLS):
            if not self._scroll(down=False):
                return

    # ── 항목 처리 ────────────────────────────────
    def _find_rows(self, screen, keys) -> dict[str, int]:
        g = _gray(screen)
        found = {}
        for key in keys:
            tpl = self.labels[key]
            score, (_, y) = self._match(g, tpl)
            cy = y + tpl.shape[0] // 2
            if score >= LABEL_MIN_SCORE and LIST_Y[0] + 14 <= cy <= LIST_Y[1] - 14:
                found[key] = cy
        return found

    def _cycle_done(self, screen, key, cy) -> bool:
        """'Make Stars Invisible:' 바로 뒤 첫 단어가 목표 문구인지 본다.

        'All of them'과 '75% of them'은 뒤쪽이 같아서 전체로 비교하면 0.82까지 나오므로,
        앞 단어('All')만 견본으로 두고 그 자리에서만 찾는다 (75%일 때 0.43, All일 때 1.0).
        """
        tpl = self.cycle_targets[key]
        h, w = tpl.shape
        region = _gray(screen[cy - h // 2 - 8:cy + h // 2 + 8, CYCLE_WORD_X[0]:CYCLE_WORD_X[1]])
        if region.shape[0] < h or region.shape[1] < w:
            return False
        return self._match(region, tpl)[0] >= LABEL_MIN_SCORE

    def _state_ok(self, screen, s: Setting, cy) -> bool:
        if s.cycle:
            return self._cycle_done(screen, s.key, cy)
        return is_checked(screen, cy) == (s.want == "check")

    def _apply_one(self, s: Setting, cy) -> bool:
        if s.cycle:
            # 누를 때마다 다음 단계로 바뀌므로 원하는 문구가 나올 때까지 한 번씩 누름
            for _ in range(MAX_CYCLE_TAPS):
                self.adb.tap(CHECKBOX_X, cy)
                self.sleep(0.7)
                if self._cycle_done(self.adb.screenshot(), s.key, cy):
                    return True
            return False
        for _ in range(2):
            self.adb.tap(CHECKBOX_X, cy)
            if self._wait(lambda sc: self._state_ok(sc, s, cy), timeout=2.0) is not None:
                return True
        return False

    def _process_tab(self, tab, settings: list[Setting], results):
        pending = {s.key: s for s in settings}
        self._to_top()
        for _ in range(MAX_SCROLLS):
            screen = self.adb.screenshot()
            for key, cy in self._find_rows(screen, pending).items():
                s = pending.pop(key)
                name = f"{s.section} › {s.label}"
                if self._state_ok(screen, s, cy):
                    results[key] = OK
                    self.log(f"{name}: 정상 ({s.want_text})")
                elif self._apply_one(s, cy):
                    results[key] = FIXED
                    self.log(f"{name}: 바꿨습니다 → {s.want_text}")
                else:
                    results[key] = FAILED
                    self.log(f"{name}: 바꾸지 못했습니다 → {s.want_text}", problem=True)
                screen = self.adb.screenshot()
            if not pending or not self._scroll(down=True):
                break
        for s in pending.values():
            self.log(f"{s.section} › {s.label}: 항목을 찾지 못했습니다.", problem=True)

    # ── 실행 ─────────────────────────────────────
    def run(self, keys: list[str]) -> dict[str, str]:
        targets = [ALL_SETTINGS[k] for k in keys]
        results = {k: MISSING for k in keys}
        if not self._open_options():
            self._go_home()
            return results
        by_tab: dict[str, list[Setting]] = {}
        for s in targets:
            by_tab.setdefault(s.tab, []).append(s)
        for tab, settings in by_tab.items():
            if self._open_tab(tab):
                self._process_tab(tab, settings, results)
        if self._go_home():
            self.log("설정 화면을 닫고 홈 화면으로 돌아왔습니다.")
        else:
            self.log("홈 화면 복귀를 확인하지 못했습니다.", problem=True)
        return results


class GameSettingsRunner(threading.Thread):
    """GUI가 멈추지 않도록 별도 스레드에서 한 번 실행한다."""

    def __init__(self, cfg: dict, keys: list[str], title: str, log: Callable[[str], str],
                 on_done: Callable[[dict[str, str]], None]):
        super().__init__(daemon=True)
        self.cfg, self.keys, self.title, self.on_done = cfg, keys, title, on_done
        self.log = DebugLogger(cfg, log, prefix="[Setup] ")

    def run(self):
        results = {k: MISSING for k in self.keys}
        self.log.begin()
        try:
            a = self.cfg["adb"]
            adb = Adb(a["path"], a.get("serial", ""), int(a.get("tap_press_ms", 0)))
            self.log.adb = adb
            self.log(f"{self.title} 확인을 시작합니다.")
            results = GameSettingsTask(adb, self.log, time.sleep).run(self.keys)
        except AdbError as e:
            self.log(f"ADB 오류: {e}", problem=True)
        except Exception as e:
            self.log(f"예상하지 못한 오류: {type(e).__name__}: {e}", problem=True)
        self.log.end()
        self.on_done(results)
