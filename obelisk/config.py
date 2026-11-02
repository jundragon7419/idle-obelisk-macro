"""설정 로드/저장.

config.default.json(레포에 포함)을 기본값으로 쓰고, 사용자가 바꾼 값은
config.json(git 제외)에 저장한다. 새 버전에서 항목이 늘어나도 기본값이 채워진다.
"""
import copy
import json

from .paths import DEFAULT_CONFIG, USER_CONFIG


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load() -> dict:
    cfg = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    if USER_CONFIG.exists():
        try:
            cfg = _merge(cfg, json.loads(USER_CONFIG.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass  # 깨진 설정 파일은 무시하고 기본값 사용
    return cfg


def save(cfg: dict):
    USER_CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
