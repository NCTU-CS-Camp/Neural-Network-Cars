"""Static skin catalog. Each skin declares its render mode so both a tinted
base sprite and a loaded PNG image work.

render dict shapes:
  {"type": "tint",  "base": "white"|"green", "color": (r, g, b)}
  {"type": "image", "path": "Images/Skins/<tier>/<name>"}  # loads <path>_small.png / <path>_big.png

Skin id 0 is the free stock white car (tier "DEFAULT"). "DEFAULT" is not one of
the gacha tiers (see config.TIERS), so the starter car is never drawn from the
gacha pool. All other skins are real art under Images/Skins/<tier>/.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Skin:
    id: int
    name: str
    tier: str
    render: dict[str, Any]


def _image(tier: str, slug: str, rotate: float = 0) -> dict[str, Any]:
    """`rotate` (degrees, CCW) corrects art that isn't drawn top-down nose-up,
    since the engine spins the sprite by the car's heading."""
    render: dict[str, Any] = {"type": "image", "path": f"Images/Skins/{tier}/{slug}"}
    if rotate:
        render["rotate"] = rotate
    return render


# id 0 is the always-owned stock car; ids 1+ are the gacha roster by tier.
SKINS: list[Skin] = [
    Skin(0, "原廠白車", "DEFAULT", {"type": "tint", "base": "white", "color": (255, 255, 255)}),
    # C
    Skin(1, "藍", "C", _image("C", "blue")),
    Skin(2, "黑", "C", _image("C", "black")),
    Skin(3, "橙", "C", _image("C", "orange")),
    Skin(4, "紫", "C", _image("C", "purple")),
    Skin(5, "紅", "C", _image("C", "red")),
    Skin(6, "黃", "C", _image("C", "yellow")),
    # B
    Skin(7, "頭文字D", "B", _image("B", "initiald", rotate=-90)),
    Skin(8, "跑跑卡丁車", "B", _image("B", "kartrider")),
    Skin(9, "馬力歐賽車", "B", _image("B", "mariokart")),
    Skin(10, "閃電麥坤", "B", _image("B", "mcqueen", rotate=90)),
    Skin(11, "天竺鼠車車", "B", _image("B", "molcar", rotate=90)),
    # A
    Skin(12, "F1 法拉利", "A", _image("A", "f1_ferrari")),
    Skin(13, "F1 邁凱倫", "A", _image("A", "f1_mclaren", rotate=180)),
    Skin(14, "F1 賓士", "A", _image("A", "f1_mercedes")),
    Skin(15, "F1 紅牛", "A", _image("A", "f1_redbull")),
    # S
    Skin(16, "勞大", "S", _image("S", "boss")),
    Skin(17, "巨人", "S", _image("S", "colossal_titan")),
    Skin(18, "波力", "S", _image("S", "poli")),
    # SR
    Skin(19, "蛋蛋67", "SR", _image("SR", "egg67")),
    Skin(21, "郁朝北鼻來悲茶的臉", "SR", _image("SR", "beicha")),
]

# Per-tier accent color, shared by the shop grid, 圖鑑, and reveal so a tier
# always reads the same everywhere.
TIER_COLORS: dict[str, tuple[int, int, int]] = {
    "SR": (200, 130, 255),
    "S": (255, 120, 160),
    "A": (120, 200, 255),
    "B": (150, 210, 150),
    "C": (180, 180, 180),
    "DEFAULT": (200, 200, 200),
}

_BY_ID: dict[int, Skin] = {skin.id: skin for skin in SKINS}


def all_skins() -> list[Skin]:
    return list(SKINS)


def get_skin(skin_id: int) -> Skin:
    """Return the skin, falling back to the default (id 0) if unknown."""
    return _BY_ID.get(skin_id, _BY_ID[0])


def skins_by_tier(tier: str) -> list[Skin]:
    return [skin for skin in SKINS if skin.tier == tier]
