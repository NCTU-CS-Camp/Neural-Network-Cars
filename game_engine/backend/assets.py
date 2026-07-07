from dataclasses import dataclass

import pygame

from game_engine.backend.settings import (
    CAR_RENDER_SCALE,
    DEFAULT_TRACK_BACK_PATH,
    DEFAULT_TRACK_FRONT_PATH,
    SPRITES_DIR,
)


@dataclass
class GameAssets:
    white_small_car: pygame.Surface
    white_big_car: pygame.Surface
    green_small_car: pygame.Surface
    green_big_car: pygame.Surface
    bg: pygame.Surface
    bg4: pygame.Surface


def _car_sprite(name: str) -> pygame.Surface:
    """Load a car sprite and scale it for display (visual only; collision is
    fixed in car.py). smoothscale keeps edges clean when enlarged."""
    surface = pygame.image.load(SPRITES_DIR / name)
    if CAR_RENDER_SCALE == 1.0:
        return surface
    w, h = surface.get_size()
    return pygame.transform.smoothscale(
        surface, (round(w * CAR_RENDER_SCALE), round(h * CAR_RENDER_SCALE))
    )


def load_game_assets():
    return GameAssets(
        white_small_car=_car_sprite("white_small.png"),
        white_big_car=_car_sprite("white_big.png"),
        green_small_car=_car_sprite("green_small.png"),
        green_big_car=_car_sprite("green_big.png"),
        bg=pygame.image.load(DEFAULT_TRACK_FRONT_PATH),
        bg4=pygame.image.load(DEFAULT_TRACK_BACK_PATH),
    )
