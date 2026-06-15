from dataclasses import dataclass

import pygame

from game_engine.backend.settings import PROJECT_ROOT, SPRITES_DIR


@dataclass
class GameAssets:
    white_small_car: pygame.Surface
    white_big_car: pygame.Surface
    green_small_car: pygame.Surface
    green_big_car: pygame.Surface
    bg: pygame.Surface
    bg4: pygame.Surface


def load_game_assets():
    return GameAssets(
        white_small_car=pygame.image.load(SPRITES_DIR / "white_small.png"),
        white_big_car=pygame.image.load(SPRITES_DIR / "white_big.png"),
        green_small_car=pygame.image.load(SPRITES_DIR / "green_small.png"),
        green_big_car=pygame.image.load(SPRITES_DIR / "green_big.png"),
        bg=pygame.image.load(PROJECT_ROOT / "bg7.png"),
        bg4=pygame.image.load(PROJECT_ROOT / "bg4.png"),
    )
