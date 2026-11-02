"""게임 설정 확인 및 적용 (Options → Gameplay → Lootbugs & Freebies).

매크로가 동작하려면 다음 설정이 필요하다.
  체크:  Auto-Loot free Lootbug offerings
  해제:  Remove Lootbug Gem confirmation
  체크:  Enable Loot-All Banked Lootbugs
  체크:  Tap any Lootbug to Loot-All
  체크:  One Click Claim all Banked Freebies

흐름: 홈 하단 가운데 메뉴 버튼 → Options → Gameplay 탭 → 항목 라벨을 찾아
체크 상태 확인 → 다르면 체크박스를 한 번 탭하고 반영 확인 → X로 닫고 홈 복귀.
"""
import threading
import time
from dataclasses import dataclass
from typing import Callable

import cv2

from ..core import screen as scr
from ..core.adb import Adb, AdbError
from ..core.debuglog import DebugLogger
from ..core.imaging import imread
from ..paths import TEMPLATES

MENU_BTN = (360, 1210)             # 홈 하단 가운데 네모 4개 버튼
GAMEPLAY_TAB = (308, 121)
GAMEPLAY_TAB_ROI = (262, 100, 355, 143)
TABS_ROI = (52, 100, 668, 143)     # All / General / Gameplay / Display / Offline / Menus
CHECKBOX_X = 78
LABEL_MIN_SCORE = 0.8              # 같은 화면의 다른 라벨과는 0.6 이하
OPTIONS_MIN_SCORE = 0.85


@dataclass(frozen=True)
class Setting:
    key: str
    label: str
    required: bool  # True면 체크, False면 해제


SETTINGS = [
    Setting("auto_loot_free", "Auto-Loot free Lootbug offerings", True),
    Setting("remove_gem_confirm", "Remove Lootbug Gem confirmation", False),
    Setting("loot_all_banked", "Enable Loot-All Banked Lootbugs", True),
    Setting("tap_any_loot_all", "Tap any Lootbug to Loot-All", True),
    Setting("one_click_freebies", "One Click Claim all Banked Freebies", True),
]

# 결과 코드
OK, FIXED, FAILED, MISSING = "ok", "fixed", "failed", "missing"


def _gray(img):
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def _ratio(img, roi, lo_h, hi_h):
    x1, y1, x2, y2 = roi
    hsv = cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2HSV)
    m = (hsv[..., 0] >= lo_h) & (hsv[..., 0] <= hi_h) & (hsv[..., 1] > 120) & (hsv[..., 2] > 120)
    return float(m.mean())


def is_checked(screen, cy) -> bool:
    """체크박스 안 흰 체크 표시 비율 (체크 0.38~0.39, 빈칸 0.00)."""
    box = screen[cy - 14:cy + 14, CHECKBOX_X - 14:CHECKBOX_X + 14]
    return float((box.min(axis=2) > 200).mean()) > 0.2


class GameSettingsTask:
    def __init__(self, adb, log, sleep):
        self.adb, self.log, self.sleep = adb, log, sleep
        self.options_icon = _gray(imread(TEMPLATES / "ui" / "options_icon.png"))
        self.labels = {s.key: _gray(imread(TEMPLATES / "ui" / f"setting_{s.key}.png"))
                       for s in SETTINGS}

    # ── 화면 판별 ────────────────────────────────
    def _match(self, screen, tpl):
        r = cv2.matchTemplate(_gray(screen), tpl, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(r)
        return score, loc

    def _options_open(self, screen) -> bool:
        """설정 화면 상단의 탭 버튼 줄(빨강/초록)이 보이면 설정 화면."""
        return scr.menu_open(screen) and (
            _ratio(screen, TABS_ROI, 0, 8) + _ratio(screen, TABS_ROI, 170, 180)
            + _ratio(screen, TABS_ROI, 40, 85)) > 0.4

    def _gameplay_active(self, screen) -> bool:
        return _ratio(screen, GAMEPLAY_TAB_ROI, 40, 85) > 0.4

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

    def _open_gameplay(self) -> bool:
        screen = self.adb.screenshot()
        if not self._options_open(screen):
            if not scr.at_home(screen) and not self._go_home():
                self.log("홈 화면으로 돌아오지 못해 설정 화면을 열 수 없습니다.")
                return False
            self.adb.tap(*MENU_BTN)
            screen = self._wait(lambda s: self._match(s, self.options_icon)[0] >= OPTIONS_MIN_SCORE)
            if screen is None:
                self.log("메뉴에서 Options 버튼을 찾지 못했습니다.")
                return False
            _, (x, y) = self._match(screen, self.options_icon)
            h, w = self.options_icon.shape
            self.adb.tap(x + w // 2, y + h // 3)  # 아이콘 부분
            if self._wait(self._options_open) is None:
                self.log("Options 화면이 열리지 않았습니다.")
                return False
        self.adb.tap(*GAMEPLAY_TAB)
        if self._wait(self._gameplay_active, timeout=2.0) is None:
            self.log("Gameplay 탭으로 바뀌지 않았습니다.")
            return False
        self.sleep(0.5)
        return True

    def _find_rows(self) -> dict[str, int]:
        """항목 라벨을 찾아 체크박스 중심 y를 돌려준다. 다 못 찾으면 아래로 스크롤하며 찾는다."""
        found: dict[str, int] = {}
        for attempt in range(4):
            screen = self.adb.screenshot()
            found = {}
            for key, tpl in self.labels.items():
                score, (_, y) = self._match(screen, tpl)
                if score >= LABEL_MIN_SCORE and 150 < y < 1000:
                    found[key] = y + tpl.shape[0] // 2
            if len(found) == len(SETTINGS):
                return found
            self.adb.swipe(360, 850, 360, 500, 600)
            self.sleep(1.0)
        return found

    def _toggle(self, cy, want) -> bool:
        for _ in range(2):
            self.adb.tap(CHECKBOX_X, cy)
            if self._wait(lambda s: is_checked(s, cy) == want, timeout=2.0) is not None:
                return True
        return False

    # ── 실행 ─────────────────────────────────────
    def run(self) -> dict[str, str]:
        results = {s.key: MISSING for s in SETTINGS}
        if not self._open_gameplay():
            self._go_home()
            return results
        rows = self._find_rows()
        screen = self.adb.screenshot()
        for s in SETTINGS:
            if s.key not in rows:
                self.log(f"{s.label}: 항목을 찾지 못했습니다.")
                continue
            cy = rows[s.key]
            state = is_checked(screen, cy)
            want_txt = "체크" if s.required else "해제"
            if state == s.required:
                results[s.key] = OK
                self.log(f"{s.label}: 정상 ({want_txt})")
            elif self._toggle(cy, s.required):
                results[s.key] = FIXED
                self.log(f"{s.label}: {want_txt}로 바꿨습니다.")
            else:
                results[s.key] = FAILED
                self.log(f"{s.label}: {want_txt}로 바꾸지 못했습니다.")
        if self._go_home():
            self.log("설정 화면을 닫고 홈 화면으로 돌아왔습니다.")
        else:
            self.log("홈 화면 복귀를 확인하지 못했습니다.")
        return results


class GameSettingsRunner(threading.Thread):
    """GUI가 멈추지 않도록 별도 스레드에서 한 번 실행한다."""

    def __init__(self, cfg: dict, log: Callable[[str], str],
                 on_done: Callable[[dict[str, str]], None]):
        super().__init__(daemon=True)
        self.cfg, self.on_done = cfg, on_done
        self.log = DebugLogger(cfg, log, prefix="[Setup] ")

    def run(self):
        results = {s.key: MISSING for s in SETTINGS}
        try:
            a = self.cfg["adb"]
            adb = Adb(a["path"], a.get("serial", ""), int(a.get("tap_press_ms", 0)))
            self.log.adb = adb
            self.log("게임 설정 확인을 시작합니다.")
            results = GameSettingsTask(adb, self.log, time.sleep).run()
        except AdbError as e:
            self.log(f"ADB 오류: {e}")
        except Exception as e:
            self.log(f"예상하지 못한 오류: {type(e).__name__}: {e}")
        self.on_done(results)
