"""프리비 팩 관련 화면 인식."""
from dataclasses import dataclass

import cv2
import numpy as np

from ...core.imaging import imread
from ...paths import TEMPLATES

SHOP_BTN = (612, 1210)                 # 홈 화면 오른쪽 아래 상점 버튼
LEVEL_ROI = (582, 1190, 644, 1240)     # 상점 버튼 안에서 초록 막대가 차오르는 영역
CLAIM_OFFSET = (413, 41)               # Freebie Pack 라벨 왼쪽 위 기준 Claim 버튼 위치
CLAIM_SIZE = (100, 69)
LABEL_MIN_SCORE = 0.9                  # 다른 팩 라벨과의 최고 유사도가 0.76이라 여유를 둠


@dataclass
class FreebieRow:
    label_xy: tuple[int, int]
    claim_center: tuple[int, int]
    claim_active: bool
    score: float


def green_level(screen) -> int:
    """상점 버튼의 초록 막대 높이(px). 쌓인 프리비가 많을수록 높다 (5/35일 때 약 6px)."""
    x1, y1, x2, y2 = LEVEL_ROI
    roi = screen[y1:y2, x1:x2].astype(np.int16)
    b, g, r = roi[..., 0], roi[..., 1], roi[..., 2]
    green = (r < 45) & (g >= 60) & (g >= b)
    return int((green.mean(axis=1) > 0.5).sum())


class FreebieVision:
    def __init__(self):
        self.label = cv2.cvtColor(imread(TEMPLATES / "ui" / "freebie_label.png"),
                                  cv2.COLOR_BGR2GRAY)

    def find_row(self, screen) -> FreebieRow | None:
        gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        r = cv2.matchTemplate(gray, self.label, cv2.TM_CCOEFF_NORMED)
        _, score, _, (x, y) = cv2.minMaxLoc(r)
        if score < LABEL_MIN_SCORE:
            return None
        bx, by = x + CLAIM_OFFSET[0], y + CLAIM_OFFSET[1]
        bw, bh = CLAIM_SIZE
        if by + bh > screen.shape[0]:
            return None  # 버튼이 화면 밖으로 잘림
        return FreebieRow((x, y), (bx + bw // 2, by + bh // 2),
                          self.claim_active(screen, bx, by), float(score))

    @staticmethod
    def claim_active(screen, bx, by) -> bool:
        """Claim 버튼이 밝은 초록이면 받을 수 있는 상태."""
        bw, bh = CLAIM_SIZE
        hsv = cv2.cvtColor(screen[by:by + bh, bx:bx + bw], cv2.COLOR_BGR2HSV)
        green = (hsv[..., 0] >= 40) & (hsv[..., 0] <= 85) & (hsv[..., 1] > 120) & (hsv[..., 2] > 120)
        return float(green.mean()) > 0.3
