"""폭탄 가방 화면 판별. 모든 좌표와 견본은 게임 원래 픽셀(540×960) 기준.

- 가방 버튼: 오른쪽 아래. 스킨 8종의 닫힘/열림 견본(위키 이미지를 2배)과 비교
- 폭탄 칸: 가방이 열리면 보이는 윗줄 왼쪽 4칸 (Gem, Cherry, Battery, D20)
- 선택된 칸: 노란 테두리
- 발사 방식 버튼: 토끼(Fire) / 거북(Fire Slow) / 핵폭발(Fire All). 누를 때마다 바뀜
"""
from dataclasses import dataclass

import cv2
import numpy as np

from ...core.imaging import imread, to_540
from ...paths import TEMPLATES

ROOT = TEMPLATES / "bombs"

BAG_BTN = (490, 780)                 # 가방 버튼 중심
BAG_ROI = (446, 736, 534, 824)       # 가방 견본(48×48)을 찾는 범위
SLOT_X = {"gem": 63, "cherry": 117, "battery": 171, "d20": 225}   # 윗줄 칸의 왼쪽 끝
SLOT_Y = 661
SLOT_SIZE = 44
MODE_BTN = (395, 798)
MODE_ROI = (383, 789, 408, 809)
FIRE_BTN = (395, 850)
COUNT_ROI_H = (30, 44)               # 칸 안 숫자 줄 (칸 위쪽 기준 y 범위)

BOMB_NAMES = {"gem": "Gem Bomb", "cherry": "Cherry Bomb", "battery": "Battery Bomb",
              "d20": "D20 Bomb"}
ORDERS = {
    "cherry_first": ["cherry", "gem", "battery", "d20"],
    "gem_first": ["gem", "cherry", "battery", "d20"],
}
MODES = ("nuke", "rabbit", "turtle")
MODE_NAMES = {"nuke": "Fire All", "rabbit": "Fire", "turtle": "Fire Slow"}
TOL = 40
# 연속 캡처(H.264)에서는 압축 때문에 같은 그림도 점수가 0.8대로 내려간다(일반 캡처는 1.00).
# 그래서 고정 기준 대신 '가장 비슷한 것이 MIN_SCORE 이상이고 2등보다 MIN_MARGIN 이상 높음'으로 판정한다.
MIN_SCORE = 0.7
MIN_MARGIN = 0.15


def pick(scores: dict[str, float]) -> str | None:
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    (k1, s1), (_, s2) = ranked[0], ranked[1]
    return k1 if s1 >= MIN_SCORE and s1 - s2 >= MIN_MARGIN else None


def inlier(a, b, mask=None, tol=TOL) -> float:
    ok = np.abs(a.astype(np.int16) - b.astype(np.int16)).max(axis=2) <= tol
    return float(ok[mask].mean() if mask is not None else ok.mean())


@dataclass
class BagState:
    opened: bool | None     # None이면 가방 버튼을 못 찾음
    skin: str | None
    score: float


class BombVision:
    def __init__(self):
        self.bags = []   # (스킨, 열림 여부, bgr, mask, 3채널 mask)
        for p in sorted((ROOT / "bag").glob("*.png")):
            skin, state = p.stem.rsplit("_", 1)
            rgba = imread(p, cv2.IMREAD_UNCHANGED)
            mask = rgba[..., 3] > 0
            m3 = cv2.merge([mask.astype(np.uint8)] * 3)
            self.bags.append((skin, state == "opened", rgba[..., :3].copy(), mask, m3))
        self.icons = {k: imread(ROOT / f"icon_{k}.png") for k in SLOT_X}
        self.modes = {k: imread(ROOT / f"mode_{k}.png") for k in MODES}

    # ── 가방 ─────────────────────────────────────
    def bag(self, screen720, min_score=0.75) -> BagState:
        img = to_540(screen720)
        x1, y1, x2, y2 = BAG_ROI
        roi = img[y1:y2, x1:x2]
        best = BagState(None, None, 0.0)
        for skin, opened, bgr, mask, m3 in self.bags:
            r = cv2.matchTemplate(roi, bgr, cv2.TM_SQDIFF, mask=m3)
            _, _, (x, y), _ = cv2.minMaxLoc(np.nan_to_num(r, nan=np.inf))
            h, w = mask.shape
            s = inlier(roi[y:y + h, x:x + w], bgr, mask)
            if s > best.score:
                best = BagState(opened, skin, s)
        if best.score < min_score:
            return BagState(None, best.skin, best.score)
        return best

    # ── 폭탄 칸 ──────────────────────────────────
    def slot_scores(self, screen720, key) -> dict[str, float]:
        img = to_540(screen720)
        x = SLOT_X[key]
        patch = img[SLOT_Y + 2:SLOT_Y + 30, x + 2:x + 42]
        return {k: inlier(patch, t) for k, t in self.icons.items()}

    def slots_ok(self, screen720) -> dict[str, str]:
        """4칸이 예상한 폭탄인지. 맞지 않는 칸만 {칸: 판별 결과 설명}으로 돌려준다."""
        wrong = {}
        for key in SLOT_X:
            sc = self.slot_scores(screen720, key)
            got = pick(sc)
            if got != key:
                best = max(sc, key=sc.get)
                wrong[key] = f"{sc[key]:.2f} (가장 비슷한 것 {best} {sc[best]:.2f})"
        return wrong

    @staticmethod
    def selected(screen720) -> str | None:
        """노란 테두리가 있는 칸 (윗줄 4칸 중)."""
        img = to_540(screen720).astype(np.int16)
        best, best_v = None, 0.0
        for k, x in SLOT_X.items():
            b = img[SLOT_Y - 2:SLOT_Y + SLOT_SIZE + 3, x - 2:x + SLOT_SIZE + 2]
            ring = np.ones(b.shape[:2], bool)
            ring[4:-4, 4:-4] = False
            p = b[ring]
            v = float(((p[:, 2] > 200) & (p[:, 1] > 150) & (p[:, 0] < 120)).mean())
            if v > best_v:
                best, best_v = k, v
        return best if best_v > 0.3 else None

    @staticmethod
    def count_changed(before, after) -> bool:
        """남은 개수 숫자가 바뀌었는지 (압축 없는 화면끼리 비교: 숫자 한 자리만 바뀌어도
        밝기 차 80 넘는 픽셀이 수십 개 생김). 발사 방식 버튼 비교에도 쓴다."""
        return int((np.abs(after.astype(np.int16) - before.astype(np.int16)).max(axis=2) > 80).sum()) >= 6

    @staticmethod
    def count_patch(screen720, key):
        img = to_540(screen720)
        x = SLOT_X[key]
        return img[SLOT_Y + COUNT_ROI_H[0]:SLOT_Y + COUNT_ROI_H[1], x + 2:x + 42].copy()

    # ── 발사 방식 ────────────────────────────────
    @staticmethod
    def mode_patch(screen720):
        x1, y1, x2, y2 = MODE_ROI
        return to_540(screen720)[y1:y2, x1:x2].copy()

    def mode(self, screen720) -> str | None:
        img = to_540(screen720)
        x1, y1, x2, y2 = MODE_ROI
        patch = img[y1:y2, x1:x2]
        sc = {k: inlier(patch, t) for k, t in self.modes.items()}
        # 필요한 건 핵폭발(Fire All)인지 아닌지뿐이다. 토끼와 거북은 서로 닮아서(0.73)
        # 압축 잡음이 있으면 둘을 가르기 어려우므로 둘을 묶어서 핵폭발과 비교한다.
        other = max(sc["rabbit"], sc["turtle"])
        if sc["nuke"] >= MIN_SCORE and sc["nuke"] - other >= MIN_MARGIN:
            return "nuke"
        if other >= MIN_SCORE and other - sc["nuke"] >= MIN_MARGIN:
            return "rabbit" if sc["rabbit"] >= sc["turtle"] else "turtle"
        return None
