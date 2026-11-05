"""게임 글꼴(흰색 글자) 숫자 읽기.

게임 글자는 가장자리가 회색으로 부드럽게 그려져서(안티앨리어싱), 화면 위치에 따라
같은 숫자도 흑백으로 자르면 폭이 6px/7px로 달라진다. 그래서 회색 값을 그대로 살린
글자 이미지를 같은 크기로 맞춘 뒤 정규화 상관으로 견본과 비교한다.

게임은 270×480 화면을 2.667배로 늘려 그리므로 원래 한 픽셀이 화면에서 2칸 또는 3칸이
된다. 어느 쪽이 될지는 글자 위치에 따라 달라서 견본과 모양이 어긋날 수 있다. 그래서 먼저
같은 값이 이어지는 줄과 칸을 하나로 접어 원래 크기의 모양으로 바꾼 뒤 견본과 비교하고
(위치와 상관없이 같은 글자는 같은 모양이 됨), 맞는 것이 없을 때만 상관 비교를 쓴다.

견본: assets/templates/digits/<글자>_<번호>.png ('/'는 slash)
"""
import cv2
import numpy as np

from ..paths import TEMPLATES
from .imaging import imread

SIZE = (10, 20)          # 비교용 크기 (w, h)
ON = 100                 # 글자 픽셀로 볼 밝기 (RGB 최솟값 기준)
MIN_SCORE = 0.75         # 견본끼리 서로 맞혀 본 최저 점수 0.76
MIN_MARGIN = 0.05        # 1위와 2위 글자의 점수 차 (견본 기준 최소 0.08)

_TEMPLATES: list[tuple[str, np.ndarray]] | None = None
_FOLDED: list[tuple[str, np.ndarray]] | None = None
FOLD_TOL = 40            # 같은 줄로 볼 밝기 차
FOLD_MAX_DIFF = 12       # 접은 모양의 평균 밝기 차가 이 이하이면 그 글자 (견본끼리는 0, 다른 글자끼리는 최소 21)
FOLD_MIN_MARGIN = 8


def fold(glyph: np.ndarray) -> np.ndarray:
    """이어지는 같은 줄/칸을 하나로 접는다 (확대 배율 차이 제거)."""
    g = glyph.astype(np.int16)
    for axis in (0, 1):
        keep = [0]
        for i in range(1, g.shape[axis]):
            if np.abs(np.take(g, i, axis) - np.take(g, keep[-1], axis)).max() > FOLD_TOL:
                keep.append(i)
        g = np.take(g, keep, axis)
    return g


def _feature(glyph: np.ndarray) -> np.ndarray:
    f = cv2.resize(glyph.astype(np.float32), SIZE, interpolation=cv2.INTER_AREA)
    f -= f.mean()
    n = np.linalg.norm(f)
    return f / n if n else f


def _load() -> list[tuple[str, np.ndarray]]:
    out = []
    for p in sorted((TEMPLATES / "digits").glob("*.png")):
        name = p.stem.split("_")[0]
        out.append(("/" if name == "slash" else name, _feature(imread(p, cv2.IMREAD_GRAYSCALE))))
    return out


def split_glyphs(region) -> list[tuple[int, np.ndarray]]:
    """흰 글자를 세로 빈 줄 기준으로 나눠 (x, 회색 글자 이미지) 목록을 돌려준다."""
    gray = region.min(axis=2)
    on = gray > ON
    cols = on.any(axis=0)
    out, x = [], 0
    while x < len(cols):
        if cols[x]:
            s = x
            while x < len(cols) and cols[x]:
                x += 1
            sub = gray[:, max(0, s - 1):x + 1]
            rows = np.where((sub > ON).any(axis=1))[0]
            out.append((s, sub[max(0, rows.min() - 1):rows.max() + 2]))
        x += 1
    return out


def _classify_folded(glyph: np.ndarray) -> tuple[str | None, float]:
    global _FOLDED
    if _FOLDED is None:
        _FOLDED = [(p.stem.split("_")[0].replace("slash", "/"),
                    fold(imread(p, cv2.IMREAD_GRAYSCALE)))
                   for p in sorted((TEMPLATES / "digits").glob("*.png"))]
    f = fold(glyph)
    best: dict[str, float] = {}
    for ch, t in _FOLDED:
        if t.shape == f.shape:
            d = float(np.abs(f - t).mean())
            if d < best.get(ch, 1e9):
                best[ch] = d
    if not best:
        return None, 0.0
    ranked = sorted(best.items(), key=lambda kv: kv[1])
    c1, d1 = ranked[0]
    d2 = ranked[1][1] if len(ranked) > 1 else 1e9
    if d1 <= FOLD_MAX_DIFF and d2 - d1 >= FOLD_MIN_MARGIN:
        return c1, 1.0 - d1 / 255
    return None, 0.0


def classify(glyph: np.ndarray) -> tuple[str | None, float]:
    global _TEMPLATES
    if _TEMPLATES is None:
        _TEMPLATES = _load()
    if glyph.shape[1] <= 4:      # ':' 같은 좁은 기호
        return None, 0.0
    c, s = _classify_folded(glyph)
    if c is not None:
        return c, s
    f = _feature(glyph)
    best: dict[str, float] = {}
    for ch, t in _TEMPLATES:
        s = float((f * t).sum())
        if s > best.get(ch, -1.0):
            best[ch] = s
    ranked = sorted(best.items(), key=lambda kv: -kv[1])
    (c1, s1), (_, s2) = ranked[0], ranked[1]
    if s1 >= MIN_SCORE and s1 - s2 >= MIN_MARGIN:
        return c1, s1
    return None, s1


def read_text(region) -> str:
    """숫자와 '/'만 읽는다. 모르는 글자는 '?'."""
    return "".join(classify(g)[0] or "?" for _, g in split_glyphs(region))
