"""게임 공통 화면 판별."""
from .imaging import red_ratio

TOOLBAR_ROI = (128, 1180, 192, 1240)   # 하단 곡괭이 버튼
TOOLBAR_X_ROI = (410, 1185, 470, 1235) # 상점 등 메뉴가 열리면 생기는 하단 X 버튼
TOOLBAR_X_BTN = (440, 1210)


def menu_open(screen) -> bool:
    """상점 같은 전체 화면 메뉴가 열려 있으면 하단 툴바에 X 버튼이 생긴다."""
    return red_ratio(screen, TOOLBAR_X_ROI) > 0.3


def at_home(screen) -> bool:
    """홈 화면 여부.

    팝업이 뜨면 하단 툴바가 어둡게 가려져 곡괭이 버튼의 빨간색이 사라지고,
    상점 같은 메뉴가 열리면 툴바에 X 버튼이 생긴다.
    """
    return red_ratio(screen, TOOLBAR_ROI) > 0.2 and not menu_open(screen)
