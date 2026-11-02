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


def red_ratio(img, roi) -> float:
    """영역 안에서 선명한 빨강(버튼 색) 픽셀 비율."""
    x1, y1, x2, y2 = roi
    hsv = cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2HSV)
    red = ((hsv[..., 0] < 8) | (hsv[..., 0] > 170)) & (hsv[..., 1] > 120) & (hsv[..., 2] > 120)
    return float(red.mean())
