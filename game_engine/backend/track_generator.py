from __future__ import annotations

import random
from pathlib import Path

import pygame

from game_engine.backend.settings import (
    SCREEN_SIZE,
    TRACK_ASSETS_DIR,
    TRACK_BACK_PATH,
    TRACK_FRONT_PATH,
)
from game_engine.backend.track_layout import (
    START_CELL,
    TrackLayout,
    cell_origin,
    generate_track_layout,
)


def generate_random_map(
    screen: pygame.Surface,
    seed: int | None = None,
) -> TrackLayout:
    layout = generate_track_layout(seed if seed is not None else random.randrange(1_000_000))
    render_track_layout(
        layout,
        front_path=TRACK_FRONT_PATH,
        back_path=TRACK_BACK_PATH,
        screen=screen,
    )
    return layout


def render_track_layout(
    layout: TrackLayout,
    *,
    front_path: Path,
    back_path: Path,
    screen: pygame.Surface | None = None,
) -> None:
    pygame.init()
    front_path.parent.mkdir(parents=True, exist_ok=True)
    back_path.parent.mkdir(parents=True, exist_ok=True)

    back_surface = pygame.Surface(SCREEN_SIZE, pygame.SRCALPHA)
    back_surface.fill((0, 0, 0, 0))
    front_surface = pygame.image.load(TRACK_ASSETS_DIR / "Background.png")

    back_tiles = _load_tiles("")
    front_tiles = _load_tiles("Top")
    initial_top = pygame.image.load(TRACK_ASSETS_DIR / "Initial.png")

    for index, cell in enumerate(layout.route_cells):
        tile_name = layout.tile_name_for(index)
        origin_x, origin_y = cell_origin(cell)
        back_surface.blit(
            back_tiles[tile_name],
            _back_tile_position(origin_x, origin_y),
        )

        if cell == START_CELL:
            front_surface.blit(
                initial_top,
                (origin_x - 20, origin_y),
            )
        else:
            front_surface.blit(
                front_tiles[tile_name],
                _front_tile_position(tile_name, origin_x, origin_y),
            )

    pygame.image.save(back_surface, back_path)
    pygame.image.save(front_surface, front_path)
    if screen is not None:
        screen.blit(front_surface, (0, 0))


def _load_tiles(suffix: str) -> dict[str, pygame.Surface]:
    return {
        tile_name: pygame.image.load(TRACK_ASSETS_DIR / f"{tile_name}{suffix}.png")
        for tile_name in (
            "Straight1",
            "Straight2",
            "Curve1",
            "Curve2",
            "Curve3",
            "Curve4",
        )
    }


def _back_tile_position(origin_x: int, origin_y: int) -> tuple[int, int]:
    return origin_x, origin_y


def _front_tile_position(
    tile_name: str,
    origin_x: int,
    origin_y: int,
) -> tuple[int, int]:
    if tile_name == "Straight1":
        return origin_x, origin_y - 20
    if tile_name == "Straight2":
        return origin_x - 20, origin_y
    return origin_x - 15, origin_y - 15


def generateRandomMap(screen: pygame.Surface) -> TrackLayout:
    return generate_random_map(screen)
