"""기능(루트버그, 프리비 등)의 공통 틀."""
from dataclasses import dataclass
from typing import Callable

from ..core.stats import Stats


@dataclass
class Context:
    """기능이 실행될 때 받는 공용 도구."""
    adb: object
    cfg: dict                      # 전체 설정 (GUI에서 바꾸면 실행 중에도 반영)
    log: Callable[..., str]          # log(msg, problem=False)
    sleep: Callable[[float], None]
    stats: Stats | None = None


class Feature:
    key = ""          # config 섹션 이름
    title = ""        # 로그에 쓰는 이름
    implemented = True

    def __init__(self, ctx: Context):
        self.ctx = ctx

    @property
    def cfg(self) -> dict:
        return self.ctx.cfg[self.key]

    @property
    def enabled(self) -> bool:
        return bool(self.cfg.get("enabled"))

    @property
    def interval(self) -> float:
        return float(self.cfg.get("check_interval_sec", 30))

    def log(self, msg: str, problem: bool = False):
        """problem=True는 예외 상황. 로그에 [!]가 붙고, Debug가 켜져 있으면 화면이 저장된다."""
        self.ctx.log(f"[{self.title}] {msg}", problem=problem)

    def count(self, key: str, n: int = 1):
        """수치 기록. key는 기능 안의 경로 (예: 'looted', 'fail.popup')."""
        if self.ctx.stats is not None and n:
            self.ctx.stats.add(f"{self.key}.{key}", n)

    def mark_claimed(self):
        if self.ctx.stats is not None:
            self.ctx.stats.mark(f"{self.key}.last_at")

    def run_once(self) -> bool:
        """한 번 확인하고 처리한다. 처리한 게 있어 곧바로 다시 확인할 필요가 있으면 True."""
        raise NotImplementedError
