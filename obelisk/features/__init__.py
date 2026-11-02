"""기능 목록. 새 기능은 여기에 추가하면 실행기와 GUI가 함께 인식한다."""
from .freebie import FreebieFeature
from .lootbug import LootbugFeature

FEATURES = [LootbugFeature, FreebieFeature]
