from __future__ import annotations

import pygame

import game_engine.backend.track_generator as track_generator
from game_engine.backend.track_layout import cell_origin


def test_random_map_seed_is_deterministic(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        track_generator,
        "TRACK_FRONT_PATH",
        tmp_path / "front.png",
    )
    monkeypatch.setattr(
        track_generator,
        "TRACK_BACK_PATH",
        tmp_path / "back.png",
    )
    monkeypatch.setattr(
        track_generator,
        "TRACK_METADATA_PATH",
        tmp_path / "track.json",
    )
    surface = pygame.Surface((1600, 900))

    first = track_generator.generate_random_map(surface, seed=12345)
    second = track_generator.generate_random_map(surface, seed=12345)
    different = track_generator.generate_random_map(surface, seed=12346)

    assert first.polyline == second.polyline
    assert first.polyline != different.polyline
    assert first.map_name == "random_seed_12345"

    collision_map = pygame.image.load(track_generator.TRACK_BACK_PATH)
    assert collision_map.get_at((0, 0)).a == 0

    curve_index = next(
        index
        for index in range(len(different.route_cells))
        if different.tile_name_for(index).startswith("Curve")
    )
    origin_x, origin_y = cell_origin(different.route_cells[curve_index])
    assert collision_map.get_at((origin_x, origin_y)).a == 0
    assert collision_map.get_at((origin_x + 73, origin_y + 73)).a == 255
