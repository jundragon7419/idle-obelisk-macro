"""여러 기능이 같이 쓰는 이미지 처리 도구.

좌표는 모두 720x1280 화면 기준이다. 게임은 가로 270픽셀로 그린 화면을
2.667배 확대해서 보여주므로, 스프라이트 매칭은 화면을 270x480으로 줄여
원본 크기 템플릿과 비교한다.
"""
from pathlib import Path

import cv2
import numpy as np

SCALE = 720 / 270
NATIVE = (270, 480)


def imread(path: Path, flags=cv2.IMREAD_COLOR):
    """한글 경로도 읽히는 imread."""
    return cv2.imdecode(np.fromfile(str(path), np.uint8), flags)


def imwrite(path: Path, img):
    cv2.imencode(path.suffix or ".png", img)[1].tofile(str(path))


# 게임은 540×960으로 그리고 720×1280에서는 4칸 중 한 칸(나머지 2)을 복제한다.
# 그 칸을 빼면 게임이 그린 픽셀 그대로 돌아온다.
_KEEP_X = np.array([i for i in range(720) if i % 4 != 2])
_KEEP_Y = np.array([i for i in range(1280) if i % 4 != 2])


def to_540(screen):
    """720×1280 화면을 게임 원래 픽셀(540×960)로 정확히 되돌린다."""
    return screen[_KEEP_Y][:, _KEEP_X]


def from_540(x, y) -> tuple[int, int]:
    """540×960 좌표를 탭에 쓰는 720×1280 좌표로."""
    return round(x * 4 / 3), round(y * 4 / 3)


def to_native(screen):
    return cv2.resize(screen, NATIVE, interpolation=cv2.INTER_AREA)


def load_rgba(path: Path, scale: float = 1.0):
    """투명 PNG를 (BGR, 마스크)로 읽는다."""
    t = imread(path, cv2.IMREAD_UNCHANGED)
    if scale != 1.0:
        t = cv2.resize(t, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return np.ascontiguousarray(t[..., :3]), t[..., 3] > 128


def inlier(img, x, y, bgr, mask, tol) -> float:
    """템플릿 픽셀 중 색 차이가 tol 이하인 픽셀 비율. 일부가 가려져도 점수가 유지된다."""
    h, w = mask.shape
    patch = img[y:y + h, x:x + w]
    if patch.shape[:2] != (h, w):
        return 0.0
    diff = np.abs(patch.astype(np.int16) - bgr.astype(np.int16)).max(axis=2)
    return float((diff <= tol)[mask].mean())


def inlier_many(img, xs, ys, bgr, mask, tol) -> np.ndarray:
    """여러 위치의 inlier 점수를 한 번에 계산한다 (Python 반복 대신 배열 연산).

    xs, ys는 패치 왼쪽 위 좌표. 이미지 밖으로 나가는 위치는 0점.
    """
    xs = np.asarray(xs, dtype=np.intp)
    ys = np.asarray(ys, dtype=np.intp)
    out = np.zeros(len(xs), dtype=np.float32)
    if len(xs) == 0:
        return out
    h, w = mask.shape
    H, W = img.shape[:2]
    ok = (xs >= 0) & (ys >= 0) & (xs + w <= W) & (ys + h <= H)
    if not ok.any():
        return out
    my, mx = np.nonzero(mask)                       # 마스크 픽셀만 모아 비교
    tpl = bgr[my, mx].astype(np.int16)              # (P, 3)
    yy = ys[ok, None] + my[None, :]                 # (N, P)
    xx = xs[ok, None] + mx[None, :]
    diff = np.abs(img[yy, xx].astype(np.int16) - tpl).max(axis=2)
    out[ok] = (diff <= tol).mean(axis=1)
    return out


def red_ratio(img, roi) -> float:
    """영역 안에서 선명한 빨강(버튼 색) 픽셀 비율."""
    x1, y1, x2, y2 = roi
    hsv = cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2HSV)
    red = ((hsv[..., 0] < 8) | (hsv[..., 0] > 170)) & (hsv[..., 1] > 120) & (hsv[..., 2] > 120)
    return float(red.mean())
