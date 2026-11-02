"""리소스와 설정 파일 경로.

PyInstaller로 묶으면 리소스는 임시 폴더(sys._MEIPASS)에 풀리고,
설정·디버그 파일은 exe 옆에 두어야 사용자가 수정할 수 있다.
"""
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    APP_ROOT = Path(sys.executable).parent
else:
    RESOURCE_ROOT = Path(__file__).resolve().parent.parent
    APP_ROOT = RESOURCE_ROOT

TEMPLATES = RESOURCE_ROOT / "assets" / "templates"
DEFAULT_CONFIG = RESOURCE_ROOT / "config.default.json"
USER_CONFIG = APP_ROOT / "config.json"
DEBUG_DIR = APP_ROOT / "debug"
