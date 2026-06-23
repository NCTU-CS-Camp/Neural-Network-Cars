from __future__ import annotations

import hashlib
import json

import pygame
from PIL import Image

from game_engine.backend import track_generator
from game_engine.backend.official_track_generator import (
    CHECKPOINT_COUNT,
    OFFICIAL_TRACK_SEEDS,
    generate_official_tracks,
)
from game_engine.backend.track_layout import (
    END_CELL,
    MIN_ROUTE_CELLS,
    START_CELL,
    build_checkpoints,
    generate_track_layout,
)


def test_seeded_track_layout_is_reproducible_and_closed():
    first = generate_track_layout(12345)
    second = generate_track_layout(12345)

    assert first == second
    assert first.route_cells[0] == START_CELL
    assert first.route_cells[-1] == END_CELL
    assert len(first.route_cells) >= MIN_ROUTE_CELLS
    assert len(set(first.route_cells)) == len(first.route_cells)
    assert first.connections_for(0) == frozenset(("N", "S"))


def test_official_seeds_create_five_distinct_layouts():
    layouts = [
        generate_track_layout(seed)
        for seed in OFFICIAL_TRACK_SEEDS.values()
    ]

    assert len(layouts) == 5
    assert len({layout.route_cells for layout in layouts}) == 5


def test_checkpoints_follow_the_generated_route():
    layout = generate_track_layout(OFFICIAL_TRACK_SEEDS["official_001"])
    checkpoints = build_checkpoints(layout, count=CHECKPOINT_COUNT)

    assert len(checkpoints) == CHECKPOINT_COUNT
    assert [checkpoint["index"] for checkpoint in checkpoints] == list(
        range(CHECKPOINT_COUNT)
    )
    assert checkpoints[-1]["center"] == [
        layout.spawn["x"],
        layout.spawn["y"],
    ]


def test_simulator_random_map_uses_seeded_shared_generator(
    tmp_path,
    monkeypatch,
):
    front_path = tmp_path / "front.png"
    back_path = tmp_path / "back.png"
    monkeypatch.setattr(track_generator, "TRACK_FRONT_PATH", front_path)
    monkeypatch.setattr(track_generator, "TRACK_BACK_PATH", back_path)
    screen = pygame.Surface((1600, 900))

    layout = track_generator.generate_random_map(screen, seed=24680)

    assert layout == generate_track_layout(24680)
    assert front_path.exists()
    assert back_path.exists()


def test_official_generator_writes_valid_front_back_and_metadata(tmp_path):
    written = generate_official_tracks(tmp_path)

    assert len(written) == 15
    assert all(path.exists() for path in written)

    back_hashes = set()
    route_seeds = set()
    for map_id, expected_seed in OFFICIAL_TRACK_SEEDS.items():
        front_path = tmp_path / f"{map_id}_front.png"
        back_path = tmp_path / f"{map_id}_back.png"
        metadata_path = tmp_path / f"{map_id}.json"

        front = Image.open(front_path)
        back = Image.open(back_path).convert("RGBA")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        alpha = back.getchannel("A")

        assert front.size == (1600, 900)
        assert back.size == (1600, 900)
        assert alpha.getpixel((0, 0)) == 0
        alpha_colors = alpha.getcolors(maxcolors=256)
        assert alpha_colors is not None
        assert {value for _, value in alpha_colors} == {0, 255}
        assert metadata["map_id"] == map_id
        assert metadata["seed"] == expected_seed
        assert len(metadata["checkpoints"]) == CHECKPOINT_COUNT

        spawn = metadata["spawn"]
        spawn_pixel = (round(spawn["x"]), round(spawn["y"]))
        assert alpha.getpixel(spawn_pixel) == 255
        for checkpoint in metadata["checkpoints"]:
            center = tuple(round(value) for value in checkpoint["center"])
            assert alpha.getpixel(center) == 255

        back_hashes.add(hashlib.sha256(back_path.read_bytes()).hexdigest())
        route_seeds.add(metadata["seed"])

    assert len(back_hashes) == 5
    assert len(route_seeds) == 5
