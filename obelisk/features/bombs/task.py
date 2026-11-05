"""폭탄 터뜨리기.

정한 간격마다 한 바퀴:
1. 홈 화면에서 오른쪽 아래 폭탄 가방을 연다 (스킨 8종의 닫힘/열림으로 판별)
2. 윗줄 왼쪽 4칸이 Gem, Cherry, Battery, D20인지 확인
3. 고른 순서대로 폭탄 칸을 누르고(노란 테두리 확인), 발사 방식이 핵폭발(Fire All)인지
   확인한 뒤 Fire All을 누른다. 발사 방식이 다르면 버튼을 눌러 핵폭발로 바꾼다.
4. 가방을 닫고 닫힘을 확인

Fire All 확인 창은 필수 게임 설정(Disable Confirmation on Fire All Bombs)으로 꺼 둔다.
"""
import time

from ...core import screen as scr
from ...core.imaging import from_540
from ..base import Feature
from .vision import (BAG_BTN, BOMB_NAMES, FIRE_BTN, MODE_BTN, ORDERS, SLOT_SIZE,
                     SLOT_X, SLOT_Y, BombVision)


def _slot_center(key) -> tuple[int, int]:
    """540 좌표의 칸 중심."""
    return SLOT_X[key] + SLOT_SIZE // 2, SLOT_Y + SLOT_SIZE // 2


class BombsFeature(Feature):
    key = "bombs"
    title = "Bombs"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.v = BombVision()

    @property
    def order(self) -> list[str]:
        return ORDERS.get(self.cfg.get("order", "cherry_first"), ORDERS["cherry_first"])

    def _shot(self):
        return self.ctx.adb.screenshot()

    def _wait(self, cond, timeout=3.0, step=0.3):
        deadline = time.monotonic() + timeout
        while True:
            screen = self._shot()
            if cond(screen):
                return screen
            if time.monotonic() > deadline:
                return None
            self.ctx.sleep(step)

    def _tap(self, xy540):
        """540 좌표를 받아 탭 (Adb는 720 좌표를 받는다)."""
        self.ctx.adb.tap(*from_540(*xy540))

    # ── 한 주기 ──────────────────────────────────
    def run_once(self) -> bool:
        screen = self._shot()
        if scr.menu_open(screen) or not scr.at_home(screen):
            return False
        bag = self.v.bag(screen)
        if bag.opened is None:
            self.count("fail.bag")
            self.log(f"폭탄 가방 버튼을 찾지 못했습니다 (가장 비슷한 스킨 {bag.skin} {bag.score:.2f}).",
                     problem=True)
            return False
        if not bag.opened:
            self._tap(BAG_BTN)
            if self._wait(lambda sc: self.v.bag(sc).opened is True) is None:
                self.count("fail.bag")
                self.log("폭탄 가방이 열리지 않았습니다. 다음 주기에 다시 시도합니다.", problem=True)
                return False
        try:
            self._round()
        finally:
            self._close_bag()
        return False

    def _round(self):
        screen = self._shot()
        wrong = self.v.slots_ok(screen)
        if wrong:
            self.count("fail.slots")
            self.log("윗줄 폭탄 칸이 예상과 다릅니다: "
                     + ", ".join(f"{BOMB_NAMES[k]} {d}" for k, d in wrong.items())
                     + ". 이번 주기는 터뜨리지 않습니다.", problem=True)
            return
        names = " → ".join(BOMB_NAMES[k] for k in self.order)
        self.log(f"폭탄 터뜨리기: {names}")
        fired = 0
        for i, key in enumerate(self.order):
            if i:
                self.ctx.sleep(float(self.cfg.get("delay_sec", 1.0)))
            if self._fire(key):
                fired += 1
        self.count("rounds")
        self.mark_claimed()
        self.log(f"한 바퀴 완료 ({fired}/{len(self.order)}종 발사 확인).")

    def _select(self, key) -> bool:
        for attempt in range(2):
            self._tap(_slot_center(key))
            if self._wait(lambda sc: self.v.selected(sc) == key, timeout=2.0) is not None:
                return True
            if attempt == 0:
                self.log(f"{BOMB_NAMES[key]}: 선택되지 않아 한 번 더 누릅니다.", problem=True)
        return False

    def _read_mode(self):
        """발사 방식 판별. 압축 잡음으로 못 읽으면 누르지 않고 다시 찍어 본다."""
        for _ in range(4):
            mode = self.v.mode(self._shot())
            if mode is not None:
                return mode
            self.ctx.sleep(0.3)
        return None

    def _ensure_fire_all(self) -> bool:
        for _ in range(4):
            mode = self._read_mode()
            if mode == "nuke":
                return True
            if mode is None:
                self.log("발사 방식 버튼을 알아보지 못했습니다.", problem=True)
                return False
            self.log("발사 방식이 Fire All이 아니라(토끼 또는 거북) 버튼을 눌러 바꿉니다.")
            before = self.v.mode_patch(self._shot())
            self._tap(MODE_BTN)
            self._wait(lambda sc: self.v.count_changed(before, self.v.mode_patch(sc)), timeout=1.5)
        return False

    def _fire(self, key) -> bool:
        name = BOMB_NAMES[key]
        if not self._select(key):
            self.count("fail.select")
            self.log(f"{name}: 칸을 선택하지 못해 건너뜁니다.", problem=True)
            return False
        if not self._ensure_fire_all():
            self.count("fail.mode")
            self.log(f"{name}: 발사 방식을 Fire All로 바꾸지 못해 건너뜁니다.", problem=True)
            return False
        # 남은 개수는 몇 자리만 바뀌기도 해서, 압축 없는 화면(screencap)으로 비교한다
        before = self.v.count_patch(self.ctx.adb.screenshot(exact=True), key)
        self._tap(FIRE_BTN)
        changed = False
        deadline = time.monotonic() + 2.0
        while not changed and time.monotonic() < deadline:
            self.ctx.sleep(0.4)
            after = self.v.count_patch(self.ctx.adb.screenshot(exact=True), key)
            changed = self.v.count_changed(before, after)
        if changed:
            self.count(f"fired.{key}")
            self.log(f"{name}: Fire All")
            return True
        # 남은 충전이 없으면 숫자가 그대로일 수 있어 실패로 세지 않는다
        self.log(f"{name}: Fire All을 눌렀지만 남은 개수 표시가 바뀌지 않았습니다 (충전이 없었을 수 있음).")
        return False

    def _close_bag(self):
        for attempt in range(2):
            if self.v.bag(self._shot()).opened is False:
                return
            self._tap(BAG_BTN)
            if self._wait(lambda sc: self.v.bag(sc).opened is False, timeout=2.0) is not None:
                return
        self.count("fail.close")
        self.log("폭탄 가방이 닫히지 않았습니다.", problem=True)

