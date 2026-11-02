"""프리비 팩 자동 수령.

1. 홈 화면 상점 버튼의 초록 막대(쌓인 프리비)가 기준 이상이면 상점 진입
2. 상점을 스크롤하며 'Freebie Pack' 라벨을 찾음
3. Claim을 한 번 탭하면 쌓인 프리비를 모두 받음 → 버튼이 비활성으로 바뀌는지 확인
4. 하단 X로 상점을 닫고 홈 화면 복귀 확인
"""
import time

from ...core import screen as scr
from ..base import Feature
from .vision import CLAIM_SIZE, SHOP_BTN, FreebieVision, green_level

SWIPE_FROM, SWIPE_TO = (360, 950), (360, 500)   # 아래로 스크롤 (손가락을 위로)
VISIBLE_Y = (110, 1165)                          # 상단 바, 하단 툴바에 가리지 않는 범위


class FreebieFeature(Feature):
    key = "freebie"
    title = "Freebie"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.v = FreebieVision()

    @property
    def detect_only(self) -> bool:
        return bool(self.cfg.get("detect_only"))

    def _shot(self):
        return self.ctx.adb.screenshot()

    def _wait(self, cond, timeout=3.0, step=0.4):
        deadline = time.monotonic() + timeout
        while True:
            screen = self._shot()
            if cond(screen):
                return screen
            if time.monotonic() > deadline:
                return None
            self.ctx.sleep(step)

    # ── 한 주기 ──────────────────────────────────
    def run_once(self) -> bool:
        screen = self._shot()
        if scr.menu_open(screen):
            self.log("메뉴가 열려 있어서 상점 안에서 이어서 진행합니다.", problem=True)
            self._claim_in_shop()
            return False
        if not scr.at_home(screen):
            return False

        level = green_level(screen)
        need = int(self.cfg.get("min_level_px", 1))
        if level < need:
            return False
        self.log(f"상점 버튼 초록 막대 {level}px (기준 {need}px) → 프리비를 받으러 갑니다.")
        if self.detect_only:
            self.log("감지만 실행 중이라 상점에 들어가지 않습니다.")
            return False

        self.ctx.adb.tap(*SHOP_BTN)
        if self._wait(scr.menu_open) is None:
            self.count("fail.shop")
            self.log("상점이 열리지 않았습니다. 다음 주기에 다시 시도합니다.", problem=True)
            return False
        self._claim_in_shop()
        return False

    # ── 상점 안 ──────────────────────────────────
    def _visible(self, row) -> bool:
        return (row is not None and row.label_xy[1] >= VISIBLE_Y[0]
                and row.claim_center[1] + 35 <= VISIBLE_Y[1])

    def _find_by_scrolling(self):
        """현재 위치에서 찾고, 없으면 아래로, 그래도 없으면 위로 스크롤하며 찾는다."""
        steps = int(self.cfg.get("max_scroll_steps", 8))
        self.ctx.sleep(0.8)
        for direction in (1, -1):
            for _ in range(steps + 1):
                row = self.v.find_row(self._shot())
                if self._visible(row):
                    return row
                if row is not None and row.label_xy[1] < VISIBLE_Y[0]:
                    # 라벨이 상단 바에 가려져 있으면 조금 올림
                    self.ctx.adb.swipe(360, 600, 360, 800, 600)
                elif row is not None:
                    # 라벨은 보이지만 버튼이 툴바 쪽에 걸쳐 있으면 조금 내림
                    self.ctx.adb.swipe(360, 800, 360, 600, 600)
                else:
                    a, b = (SWIPE_FROM, SWIPE_TO) if direction == 1 else (SWIPE_TO, SWIPE_FROM)
                    self.ctx.adb.swipe(*a, *b, 600)
                self.ctx.sleep(1.0)  # 관성 스크롤이 멈출 때까지
        return None

    def _claim_in_shop(self):
        row = self._find_by_scrolling()
        if row is None:
            self.count("fail.not_found")
            self.log("상점에서 Freebie Pack을 찾지 못했습니다.", problem=True)
        elif not row.claim_active:
            self.log("Claim 버튼이 비활성 상태입니다. 받을 프리비가 없습니다.", problem=True)
        else:
            self._claim_loop(row)
        self._close_shop()

    def _claim_loop(self, row):
        """Claim 한 번에 쌓인 프리비를 모두 받는다. 버튼이 비활성으로 바뀌면 완료.

        받은 개수는 누르기 전에 'Banked: N/최대'에서 읽는다. 받은 직후에는 보상 알림이
        라벨을 가리므로, 라벨을 다시 찾지 않고 처음 찾은 버튼 위치의 색으로 확인한다.
        """
        if row.banked is None:
            self.count("fail.count")
            self.log("Banked 개수를 읽지 못했습니다. 개수는 기록하지 않고 받습니다.", problem=True)
        else:
            self.log(f"Banked {row.banked[0]}/{row.banked[1]}")
        cx, cy = row.claim_center
        bx, by = cx - CLAIM_SIZE[0] // 2, cy - CLAIM_SIZE[1] // 2
        for attempt in range(1, 3):
            self.ctx.adb.tap(cx, cy)
            if self._wait(lambda sc: not self.v.claim_active(sc, bx, by), timeout=3.0) is not None:
                got = row.banked[0] if row.banked else 0
                self.count("claimed", got)
                self.mark_claimed()
                self.log(f"Claim 완료. 프리비 {got}개를 받았습니다." if row.banked
                         else "Claim 완료.")
                return
            if attempt == 1:
                self.log("Claim 버튼이 그대로라 한 번 더 누릅니다.", problem=True)
        self.count("fail.claim")
        self.log("Claim을 눌렀지만 버튼이 비활성으로 바뀌지 않았습니다.", problem=True)

    def _close_shop(self):
        for _ in range(3):
            screen = self._shot()
            if not scr.menu_open(screen):
                break
            self.ctx.adb.tap(*scr.TOOLBAR_X_BTN)
            self.ctx.sleep(0.8)
        if self._wait(scr.at_home, timeout=2.0) is not None:
            self.log("홈 화면 복귀 완료")
        else:
            self.log("홈 화면 복귀를 확인하지 못했습니다. 다음 주기에 다시 확인합니다.", problem=True)
