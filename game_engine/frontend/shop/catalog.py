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


def _image(tier: str, slug: str) -> dict[str, Any]:
    return {"type": "image", "path": f"Images/Skins/{tier}/{slug}"}


# id 0 is the always-owned stock car; ids 1+ are the gacha roster by tier.
SKINS: list[Skin] = [
    Skin(0, "原廠白車", "DEFAULT", {"type": "tint", "base": "white", "color": (255, 255, 255)}),
    # C
    Skin(1, "Blue", "C", _image("C", "blue")),
    Skin(2, "Green", "C", _image("C", "green")),
    Skin(3, "Orange", "C", _image("C", "orange")),
    Skin(4, "Purple", "C", _image("C", "purple")),
    Skin(5, "Red", "C", _image("C", "red")),
    Skin(6, "Yellow", "C", _image("C", "yellow")),
    # B
    Skin(7, "Initial D", "B", _image("B", "initiald")),
    Skin(8, "KartRider", "B", _image("B", "kartrider")),
    Skin(9, "Mario Kart", "B", _image("B", "mariokart")),
    Skin(10, "McQueen", "B", _image("B", "mcqueen")),
    Skin(11, "Molcar", "B", _image("B", "molcar")),
    # A
    Skin(12, "F1 Ferrari", "A", _image("A", "f1_ferrari")),
    Skin(13, "F1 McLaren", "A", _image("A", "f1_mclaren")),
    Skin(14, "F1 Mercedes", "A", _image("A", "f1_mercedes")),
    Skin(15, "F1 Red Bull", "A", _image("A", "f1_redbull")),
    # S
    Skin(16, "Boss", "S", _image("S", "boss")),
    Skin(17, "Colossal Titan", "S", _image("S", "colossal_titan")),
    Skin(18, "Poli", "S", _image("S", "poli")),
    # SR
    Skin(19, "Egg67", "SR", _image("SR", "egg67")),
    # SSR
    Skin(20, "Tadpole", "SSR", _image("SSR", "tadpole")),
]

_BY_ID: dict[int, Skin] = {skin.id: skin for skin in SKINS}


def all_skins() -> list[Skin]:
    return list(SKINS)


def get_skin(skin_id: int) -> Skin:
    """Return the skin, falling back to the default (id 0) if unknown."""
    return _BY_ID.get(skin_id, _BY_ID[0])


def skins_by_tier(tier: str) -> list[Skin]:
    return [skin for skin in SKINS if skin.tier == tier]
