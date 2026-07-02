"""Resolve a skin_id into {small, big} pygame surfaces, and apply the equipped
skin onto a GameAssets bundle. Tint mode recolors a base sprite; image mode
loads PNGs from the skin's path. Missing/broken assets fall back to the default
white sprite with a warning so the game keeps running before real art exists.

Requires the pygame display to be initialized (surfaces use convert_alpha).
"""

from __future__ import annotations

from typing import Any

import pygame

from game_engine.backend.settings import CAR_RENDER_SCALE, PROJECT_ROOT, SPRITES_DIR
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


# On-screen car heights (long axis, nose-to-tail): the base sprites are 35/55px
# tall, drawn CAR_RENDER_SCALE larger. Skins are fitted to the same heights so
# every car reads the same length regardless of its source resolution.
_TARGET_SMALL_H = round(35 * CAR_RENDER_SCALE)
_TARGET_BIG_H = round(55 * CAR_RENDER_SCALE)


def _finish(surface: pygame.Surface, rotate: float, target_h: int) -> pygame.Surface:
    """Orient then fit a sprite to ``target_h`` pixels tall, keeping aspect.

    ``rotate`` (degrees CCW) corrects art that isn't top-down nose-up — the
    engine spins the sprite by heading, so it must match the base convention.
    Fitting to a fixed height (via smoothscale) makes hi-res source art crisp at
    display size without the cars rendering huge.
    """
    if rotate:
        surface = pygame.transform.rotate(surface, rotate)
    w, h = surface.get_size()
    if h != target_h:
        surface = pygame.transform.smoothscale(
            surface, (max(1, round(w * target_h / h)), target_h)
        )
    return surface


def _crop_to_content(surface: pygame.Surface) -> pygame.Surface:
    """Trim transparent margins so the car fills its frame. Some source art sits
    tiny inside a big transparent canvas (e.g. redbug/tadpole _big at ~5-9% fill),
    which otherwise renders very small once fitted to a cell (e.g. redbull)."""
    bbox = surface.get_bounding_rect()
    if bbox.width == 0 or bbox.height == 0 or bbox.size == surface.get_size():
        return surface
    return surface.subsurface(bbox).copy()


def _render(skin_render: dict[str, Any]) -> dict[str, pygame.Surface]:
    rotate = float(skin_render.get("rotate", 0))
    if skin_render.get("type") == "image":
        path = skin_render["path"]
        small = _crop_to_content(
            pygame.image.load(str(PROJECT_ROOT / f"{path}_small.png")).convert_alpha()
        )
        big = _crop_to_content(
            pygame.image.load(str(PROJECT_ROOT / f"{path}_big.png")).convert_alpha()
        )
        # small/big feed the in-game car (rotated to nose-up so it drives right);
        # display is the full-res art in its ORIGINAL orientation for shop UI.
        return {
            "small": _finish(small, rotate, _TARGET_SMALL_H),
            "big": _finish(big, rotate, _TARGET_BIG_H),
            "display": big,
        }
    base_small, base_big = _load_base(skin_render.get("base", "white"))
    color = skin_render.get("color", (255, 255, 255))
    tinted_big = _tinted(base_big, color)
    return {
        "small": _finish(_tinted(base_small, color), rotate, _TARGET_SMALL_H),
        "big": _finish(tinted_big, rotate, _TARGET_BIG_H),
        "display": tinted_big,
    }


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


def _parent_tinted(surface: pygame.Surface) -> pygame.Surface:
    """Green-washed copy that marks parent/elite cars.

    Overlays a translucent green only on the car's own pixels (via its alpha
    mask), so the skin stays visible and the transparent background is
    untouched — the two carried-over parents read green even when skinned.
    """
    result = surface.copy()
    mask = pygame.mask.from_surface(surface)
    overlay = mask.to_surface(setcolor=(40, 220, 40, 120), unsetcolor=(0, 0, 0, 0))
    result.blit(overlay, (0, 0))
    return result


def equipped_skin_id() -> int:
    """Return the active profile's equipped catalog skin, or the default."""
    from game_engine.frontend.shop import store

    identity = store.active_identity()
    if identity is None:
        return DEFAULT_SKIN_ID
    return int(store.load_entry(identity)["equipped_skin"])


def apply_equipped_skin(assets: Any) -> None:
    """Reskin the car base sprites on a GameAssets bundle to the equipped skin.

    No-op when no profile is logged in or the default skin is equipped, so
    stock behavior is unchanged unless the player opted into a skin.
    """
    equipped = equipped_skin_id()
    if equipped == DEFAULT_SKIN_ID:
        return
    surfaces = surfaces_for(equipped)
    assets.white_small_car = surfaces["small"]
    assets.white_big_car = surfaces["big"]
    # Parent/elite cars are drawn with the green_* sprites (see
    # training_session.breed_population); green-wash the same skin so a skinned
    # run can still spot the two carried-over parents.
    assets.green_small_car = _parent_tinted(surfaces["small"])
    assets.green_big_car = _parent_tinted(surfaces["big"])
