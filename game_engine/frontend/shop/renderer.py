"""Resolve a skin_id into {small, big} pygame surfaces, and apply the equipped
skin onto a GameAssets bundle. Tint mode recolors a base sprite; image mode
loads PNGs from the skin's path. Missing/broken assets fall back to the default
white sprite with a warning so the game keeps running before real art exists.

Requires the pygame display to be initialized (surfaces use convert_alpha).
"""

from __future__ import annotations

from typing import Any

import pygame

from game_engine.backend.settings import PROJECT_ROOT, SPRITES_DIR
from game_engine.frontend.shop import catalog
from game_engine.frontend.shop.config import DEFAULT_SKIN_ID

_cache: dict[int, dict[str, pygame.Surface]] = {}


def _load_base(base: str) -> tuple[pygame.Surface, pygame.Surface]:
    color = base if base in ("white", "green") else "white"
    small = pygame.image.load(str(SPRITES_DIR / f"{color}_small.png")).convert_alpha()
    big = pygame.image.load(str(SPRITES_DIR / f"{color}_big.png")).convert_alpha()
    return small, big


def _tinted(surface: pygame.Surface, color: tuple[int, int, int]) -> pygame.Surface:
    tinted = surface.copy()
    tinted.fill((*color, 255), special_flags=pygame.BLEND_RGBA_MULT)
    return tinted


def _render(skin_render: dict[str, Any]) -> dict[str, pygame.Surface]:
    if skin_render.get("type") == "image":
        path = skin_render["path"]
        small = pygame.image.load(
            str(PROJECT_ROOT / f"{path}_small.png")
        ).convert_alpha()
        big = pygame.image.load(str(PROJECT_ROOT / f"{path}_big.png")).convert_alpha()
        return {"small": small, "big": big}
    base_small, base_big = _load_base(skin_render.get("base", "white"))
    color = skin_render.get("color", (255, 255, 255))
    return {"small": _tinted(base_small, color), "big": _tinted(base_big, color)}


def surfaces_for(skin_id: int) -> dict[str, pygame.Surface]:
    if skin_id in _cache:
        return _cache[skin_id]
    skin = catalog.get_skin(skin_id)
    try:
        result = _render(skin.render)
    except (pygame.error, FileNotFoundError, KeyError, OSError) as exc:
        print(f"[shop] skin {skin_id} render failed ({exc}); using default sprite")
        base_small, base_big = _load_base("white")
        result = {"small": base_small, "big": base_big}
    _cache[skin_id] = result
    return result


def apply_equipped_skin(assets: Any) -> None:
    """Reskin the car base sprites on a GameAssets bundle to the equipped skin.

    No-op when no profile is logged in or the default skin is equipped, so
    stock behavior is unchanged unless the player opted into a skin.
    """
    from game_engine.frontend.shop import store

    identity = store.active_identity()
    if identity is None:
        return
    equipped = int(store.load_entry(identity)["equipped_skin"])
    if equipped == DEFAULT_SKIN_ID:
        return
    surfaces = surfaces_for(equipped)
    assets.white_small_car = surfaces["small"]
    assets.green_small_car = surfaces["small"]
    assets.white_big_car = surfaces["big"]
    assets.green_big_car = surfaces["big"]
