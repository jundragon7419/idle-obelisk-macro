"""루트버그 자동 수령.

1. 홈 화면에서 루트버그 존재 확인 → 하나 탭
2. 팝업이 열렸는지 확인 (시간 초과 시 실패 처리 후 재탐색)
3. 각 행의 버프 아이콘을 읽고, 설정의 wanted_buffs와 체크 상태를 맞춤
4. Buy Checked가 활성화되어 있으면 탭 (원하는 버프가 없으면 게임이 비활성화함)
5. 하단 X로 닫고 홈 화면 복귀 확인
"""
import time
from datetime import datetime

import cv2
import numpy as np

from ...core import screen as home
from ...core.imaging import imwrite
from ...paths import DEBUG_DIR
from ..base import Feature
from .vision import BUFF_NAMES, BUY_ROI, CHECKBOX_X, CLOSE_BTN, LootbugVision

# 보상 알림이 떠오르는 영역(팝업 윗부분, 행 목록 위). 행의 남은 시간 글자는 매초 바뀌므로 제외
SETTLE_ROI = (90, 100, 630, 475)


class LootbugFeature(Feature):
    key = "lootbug"
    title = "Lootbug"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.v = LootbugVision(self.cfg)

    # ── 보조 ─────────────────────────────────────
    @property
    def detect_only(self) -> bool:
        return bool(self.cfg.get("detect_only"))

    def _shot(self):
        return self.ctx.adb.screenshot()

    def _tap(self, x, y, jitter=0):
        if not self.detect_only:
            self.ctx.adb.tap(x, y, jitter)

    def _save_debug(self, screen, bugs):
        DEBUG_DIR.mkdir(exist_ok=True)
        vis = screen.copy()
        for b in bugs:
            color = (0, 215, 255) if b.golden else (0, 255, 0)
            cv2.circle(vis, (b.x, b.y), 45, color, 3)
            cv2.putText(vis, f"{b.skin} {b.score:.2f}", (b.x - 50, b.y - 52),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        path = DEBUG_DIR / f"lootbug_{datetime.now():%Y%m%d_%H%M%S}.png"
        imwrite(path, vis)
        return path

    def _wait_popup(self):
        deadline = time.monotonic() + self.cfg.get("popup_timeout_sec", 2.0)
        self.ctx.sleep(1.0)  # 팝업 애니메이션
        while True:
            screen = self._shot()
            if self.v.popup_open(screen):
                return screen
            if time.monotonic() > deadline:
                return None
            self.ctx.sleep(0.3)

    def _settle(self, screen):
        """보상 알림이 떠오르는 동안은 팝업이 입력을 받지 않으므로, 화면이 멈출 때까지 기다린다."""
        x1, y1, x2, y2 = SETTLE_ROI
        deadline = time.monotonic() + self.cfg.get("settle_timeout_sec", 5.0)
        prev = screen
        while time.monotonic() < deadline:
            self.ctx.sleep(0.4)
            cur = self._shot()
            diff = np.abs(cur[y1:y2, x1:x2].astype(np.int16)
                          - prev[y1:y2, x1:x2].astype(np.int16)).mean()
            if diff < 1.0:
                return cur
            prev = cur
        return prev

    # ── 한 주기 ──────────────────────────────────
    def run_once(self) -> bool:
        screen = self._shot()

        if self.v.popup_open(screen):
            self.log("팝업이 열려 있어서 이어서 처리합니다.", problem=True)
            self._handle_popup(screen)
            return not self.detect_only
        if not home.at_home(screen):
            self.log("홈 화면이 아니라서 이번 주기는 건너뜁니다.", problem=True)
            return False

        bugs = self.v.find(screen)
        if not bugs:
            return False

        desc = ", ".join(f"{b.skin}{'(황금)' if b.golden else ''} {b.score:.2f}" for b in bugs)
        self.log(f"{len(bugs)}마리 발견: {desc}")

        if self.detect_only:
            path = self._save_debug(screen, bugs)
            self.log(f"감지만 실행 중이라 탭하지 않습니다. 표시 이미지: debug/{path.name}")
            return False

        target = bugs[0]
        self._tap(target.x, target.y, self.cfg.get("tap_jitter_px", 5))
        popup = self._wait_popup()
        if popup is None:
            self.count("fail.popup")
            self.log("팝업이 열리지 않았습니다. 루트버그가 움직였을 수 있어 다시 찾습니다.", problem=True)
            return True

        self.count("looted")
        self.mark_claimed()
        self._handle_popup(popup)
        return True

    # ── 팝업 처리 ────────────────────────────────
    def _want(self, row) -> bool:
        # 모르는 버프는 젬 낭비를 막기 위해 체크하지 않음
        return row.buff is not None and row.buff in set(self.cfg.get("wanted_buffs", []))

    def _toggle(self, row, want: bool) -> bool:
        """체크박스를 한 번 탭하고, 화면에 반영될 때까지 기다린다.

        반영이 늦을 때 다시 탭하면 원래대로 돌아가 버리므로 두 번 탭하지 않는다.
        """
        name = BUFF_NAMES[row.buff] if row.buff else f"{row.index + 1}번 행({row.guess}?)"
        self.log(f"  {name}: {'체크' if want else '체크 해제'}")
        if self.detect_only:
            return True
        attempts = 2
        for attempt in range(1, attempts + 1):
            self._tap(CHECKBOX_X, row.y)
            # 반영이 늦을 수 있으므로 충분히 기다린 뒤에만 다시 누른다
            deadline = time.monotonic() + self.cfg.get("toggle_timeout_sec", 2.0)
            while time.monotonic() < deadline:
                self.ctx.sleep(0.3)
                if self.v.is_checked(self._shot(), row.y) == want:
                    return True
            if attempt < attempts:
                self.log(f"  {name}: 반영되지 않아 한 번 더 누릅니다.", problem=True)
        self.log(f"  {name}: 탭했지만 체크 상태가 바뀌지 않았습니다.", problem=True)
        self.count("fail.toggle")
        return False

    def _mismatches(self, rows):
        return [r for r in rows if r.buyable and r.checked != self._want(r)]

    @staticmethod
    def _signature(rows):
        return [(r.index, r.buff, r.checked, r.buyable) for r in rows]

    def _read_stable(self, screen):
        """행 목록을 0.5초 간격으로 두 번 연속 같게 읽힐 때까지 읽는다 (최대 4번).

        팝업이 다 그려지기 전이나 알림이 지나가는 중에 읽어서 행을 놓치는 일을 막는다.
        """
        prev = None
        rows = self.v.read_rows(screen)
        for _ in range(4):
            sig = self._signature(rows)
            if sig == prev:
                return rows, screen
            prev = sig
            self.ctx.sleep(0.5)
            screen = self._shot()
            rows = self.v.read_rows(screen)
        self.log("  행 목록이 읽을 때마다 달라 마지막으로 읽은 것을 씁니다.", problem=True)
        return rows, screen

    @staticmethod
    def _gaps(rows) -> list[int]:
        """중간에 빠진 행 번호 (1부터). 행은 위에서부터 빈칸 없이 나오므로 빠졌다면 가려진 것."""
        have = {r.index for r in rows}
        return [k + 1 for k in range(max(have) + 1) if k not in have] if have else []

    def _describe(self, rows) -> str:
        return ", ".join(
            f"{BUFF_NAMES[r.buff] if r.buff else '?(' + r.guess + ')'} {r.score:.2f}"
            f"{'[v]' if r.checked else '[ ]'}{'' if r.buyable else '(구매완료)'}" for r in rows)

    def _handle_popup(self, screen):
        screen = self._settle(screen)
        rows, screen = self._read_stable(screen)
        gaps = self._gaps(rows)
        self.log(f"  팝업 행 {len(rows)}개: " + self._describe(rows),
                 problem=any(r.buff is None for r in rows) or bool(gaps))

        for row in self._mismatches(rows):
            self._toggle(row, self._want(row))

        if self.detect_only:
            self.log("  감지만 실행 중이라 Buy Checked는 누르지 않습니다.")
            return

        # 구매 직전에 다시 읽어서, 하나라도 이상하면 사지 않는다
        rows, screen = self._read_stable(self._shot())
        wrong = self._mismatches(rows)
        gaps = self._gaps(rows)
        bought = [r.buff for r in rows if r.buyable and r.checked]
        buy_on = self.v.buy_enabled(screen)
        hold = None
        if gaps:
            hold = f"{', '.join(map(str, gaps))}번 행이 가려져 읽지 못했습니다"
        elif wrong:
            hold = "설정과 다른 체크가 남아 있습니다: " + ", ".join(
                f"{BUFF_NAMES.get(r.buff, r.guess)}{'[v]' if r.checked else '[ ]'}" for r in wrong)
        elif buy_on and not bought:
            # 읽은 행에는 체크가 없는데 버튼이 켜져 있으면 못 본 행에 체크가 있다는 뜻
            hold = "읽은 행에 체크된 것이 없는데 Buy Checked가 켜져 있습니다 (못 본 행이 있음)"

        if hold:
            self.count("fail.held")
            self.log(f"  구매하지 않습니다. {hold}", problem=True)
            self.log(f"  구매 직전 행 {len(rows)}개: " + self._describe(rows), problem=True)
        elif buy_on:
            x1, y1, x2, y2 = BUY_ROI
            self._tap((x1 + x2) // 2, (y1 + y2) // 2)
            self.log("  Buy Checked 탭: " + ", ".join(BUFF_NAMES[b] for b in bought))
            self.ctx.sleep(1.0)
            if self.v.buy_enabled(self._shot()):
                self.count("fail.buy")
                self.log("  Buy Checked가 아직 활성 상태라 구매되지 않은 것으로 봅니다.", problem=True)
            else:
                for b in bought:
                    self.count(f"buffs.{b}")
        else:
            self.log("  살 버프가 없어 Buy Checked가 비활성 상태입니다.")

        self._close_popup()

    def _close_popup(self):
        screen = None
        for _ in range(self.cfg.get("max_close_retries", 3)):
            screen = self._shot()
            if not self.v.popup_open(screen):
                break
            self._tap(*CLOSE_BTN)
            self.ctx.sleep(0.8)
        else:
            screen = self._shot()
            if self.v.popup_open(screen) and self.ctx.cfg["general"].get("allow_back_key"):
                self.log("  X로 닫히지 않아 뒤로가기를 보냅니다.", problem=True)
                self.ctx.adb.back()
                self.ctx.sleep(0.8)
                screen = self._shot()

        if home.at_home(screen):
            self.log("  홈 화면 복귀 완료")
        else:
            self.log("  홈 화면 복귀를 확인하지 못했습니다. 다음 주기에 다시 확인합니다.", problem=True)
