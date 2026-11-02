"""루트버그 탐지와 루트버그 팝업 분석."""
from dataclasses import dataclass

import cv2
import numpy as np

from ...core.imaging import SCALE, imread, inlier, load_rgba, red_ratio, to_native
from ...paths import TEMPLATES

# ── 팝업 고정 좌표 (720x1280) ───────────────────────
HEADER_ROI = (125, 217, 437, 248)          # "Free/Golden Lootbug Loot:"
BUY_ROI = (262, 482, 392, 532)             # Buy Checked 버튼
CLOSE_BTN = (360, 1198)                    # 하단 X
ROW_Y0, ROW_PITCH, ROW_Y_MAX = 573, 61.33, 1100
CHECKBOX_X, ICON_X = 72, 127
SEARCH_Y = (85, 1170)                      # 상단 정보바, 하단 툴바 제외

BUFF_NAMES = {
    "item_chests": "Item Chests +3",
    "relic_chest": "Relic Chest +1",
    "cherry_charges": "Cherry Charges +100",
    "ore_income": "2x Ore Income",
    "vein_spawn": "3x Vein Spawn Rate",
    "game_speed": "2x Game Speed",
    "bomb_recharge": "10x Bomb Recharge",
    "star_spawn": "2x Star Spawn Rate",
    "auto_catch": "100% Auto-Catch",
    "archaeology": "Archaeology Banked Seconds",
    "fishing_ticks": "Fishing Ticks +12",
}


@dataclass
class Lootbug:
    x: int
    y: int
    skin: str
    golden: bool
    score: float


@dataclass
class BuffRow:
    index: int
    y: int
    buff: str | None       # 판별 실패 시 None
    score: float
    guess: str             # 점수가 가장 높았던 버프 (판별 실패해도 기록용)
    buyable: bool          # 빨간 가격 버튼이 있는 행
    checked: bool


class LootbugVision:
    def __init__(self, cfg: dict):
        self.cfg = cfg  # lootbug 섹션
        self.bugs = []
        for p in sorted((TEMPLATES / "lootbugs").glob("*.png")):
            bgr, mask = load_rgba(p)
            m3 = cv2.merge([mask.astype(np.uint8) * 255] * 3)
            skin, kind = p.stem.rsplit("_", 1)
            self.bugs.append((skin, kind == "golden", bgr, mask, m3))
        # 위키 아이콘은 2.5배 크기라 원본(16px)으로 축소
        self.buffs = {p.stem: load_rgba(p, 1 / 2.5)
                      for p in sorted((TEMPLATES / "buffs").glob("*.png"))}
        self.header = imread(TEMPLATES / "ui" / "popup_header.png").astype(np.int16)

    # ── 루트버그 ─────────────────────────────────
    def find(self, screen, topk=400) -> list[Lootbug]:
        img = to_native(screen)
        y_top, y_bot = SEARCH_Y[0] / SCALE, SEARCH_Y[1] / SCALE
        thr = self.cfg.get("min_score", 0.45)
        cands = []
        for skin, golden, bgr, mask, m3 in self.bugs:
            r = cv2.matchTemplate(img, bgr, cv2.TM_SQDIFF, mask=m3)
            r = np.nan_to_num(r, nan=np.inf, posinf=np.inf)
            local_min = cv2.erode(r, np.ones((9, 9), np.uint8))
            ys, xs = np.where(r <= local_min)
            order = np.argsort(r[ys, xs])[:topk]
            h, w = mask.shape
            for y, x in zip(ys[order], xs[order]):
                cy = y + h / 2
                if not (y_top < cy < y_bot):
                    continue
                s = inlier(img, x, y, bgr, mask, tol=40)
                if s >= thr:
                    cands.append(Lootbug(int((x + w / 2) * SCALE), int(cy * SCALE),
                                         skin, golden, s))
        cands.sort(key=lambda b: -b.score)
        kept: list[Lootbug] = []
        for c in cands:
            if all(abs(c.x - k.x) > 40 or abs(c.y - k.y) > 40 for k in kept):
                kept.append(c)
        return kept

    # ── 팝업 ─────────────────────────────────────
    def popup_open(self, screen) -> bool:
        x1, y1, x2, y2 = HEADER_ROI
        return np.abs(screen[y1:y2, x1:x2].astype(np.int16) - self.header).mean() < 25

    def buy_enabled(self, screen) -> bool:
        return red_ratio(screen, BUY_ROI) > 0.4

    @staticmethod
    def row_exists(screen, cy) -> bool:
        hsv = cv2.cvtColor(screen[cy - 24:cy + 24, CHECKBOX_X - 24:CHECKBOX_X + 24],
                           cv2.COLOR_BGR2HSV)
        orange = ((hsv[..., 0] >= 8) & (hsv[..., 0] <= 28)
                  & (hsv[..., 1] > 150) & (hsv[..., 2] > 150))
        return float(orange.mean()) > 0.1

    @staticmethod
    def is_checked(screen, cy) -> bool:
        """체크박스 안의 흰 체크 표시 비율로 판단 (체크 0.38~0.40, 빈칸 0.00)."""
        box = screen[cy - 14:cy + 14, CHECKBOX_X - 14:CHECKBOX_X + 14]
        return float((box.min(axis=2) > 200).mean()) > 0.2

    def read_rows(self, screen) -> list[BuffRow]:
        img = to_native(screen)
        min_s = self.cfg.get("buff_min_score", 0.5)
        min_margin = self.cfg.get("buff_min_margin", 0.1)
        rows = []
        for k in range(20):
            cy = int(ROW_Y0 + k * ROW_PITCH)
            if cy > ROW_Y_MAX:
                break
            # 체크박스의 주황 테두리가 없으면 목록 끝
            # (행 글자가 길면 글자색 때문에 배경 밝기로는 판단할 수 없음)
            if not self.row_exists(screen, cy):
                break
            buyable = red_ratio(screen, (445, cy - 12, 470, cy + 12)) > 0.4
            checked = self.is_checked(screen, cy)
            scores = []
            for name, (bgr, mask) in self.buffs.items():
                h, w = mask.shape
                y0 = int(cy / SCALE - h / 2)
                x0 = int(ICON_X / SCALE - w / 2)
                best = max(inlier(img, x, y, bgr, mask, tol=45)
                           for y in range(y0 - 3, y0 + 4) for x in range(x0 - 3, x0 + 4))
                scores.append((best, name))
            scores.sort(reverse=True)
            (s1, n1), (s2, _) = scores[0], scores[1]
            buff = n1 if (s1 >= min_s and s1 - s2 >= min_margin) else None
            rows.append(BuffRow(k, cy, buff, s1, n1, buyable, checked))
        return rows
