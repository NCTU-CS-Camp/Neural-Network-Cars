from __future__ import annotations

from PIL import Image

from game_engine.backend.competition_track import (
    CompetitionRunTracker,
    iter_map_metadata_paths,
    load_competition_track_metadata,
)
from game_engine.backend.track_layout import cell_center, shared_cell_edge


def test_all_current_maps_have_ordered_route_cells_and_drivable_checkpoints():
    paths = iter_map_metadata_paths()

    assert paths
    for path in paths:
        metadata = load_competition_track_metadata(path)
        assert len(metadata.route_cells) > 0
        assert len(metadata.checkpoints) == len(metadata.route_cells)

        alpha = Image.open(path.with_name(f"{path.stem}_back.png")).convert("RGBA").getchannel("A")
        for index, checkpoint in enumerate(metadata.checkpoints):
            current = metadata.route_cells[index]
            following = metadata.route_cells[(index + 1) % len(metadata.route_cells)]
            orientation, fixed_coordinate, _ = shared_cell_edge(current, following)
            for point_name in ("a", "b", "center"):
                x, y = (round(value) for value in checkpoint[point_name])
                assert alpha.getpixel((x, y)) > 0
                if orientation == "vertical":
                    assert x == fixed_coordinate
                else:
                    assert y == fixed_coordinate


def test_run_tracker_advances_only_sequential_gates_and_completes_one_lap():
    metadata = load_competition_track_metadata(iter_map_metadata_paths()[0])
    tracker = CompetitionRunTracker(
        checkpoints=metadata.checkpoints,
        total_length_px=metadata.total_length_px,
    )
    centers = [cell_center(cell) for cell in metadata.route_cells]

    tracker.advance(centers[1], centers[2], tick=1)
    assert tracker.checkpoints_completed == 0
    assert tracker.completed is False

    for index in range(len(centers)):
        previous = centers[index]
        current = centers[(index + 1) % len(centers)]
        tracker.advance(previous, current, tick=index + 2)

    assert tracker.awaiting_start_gate is True
    assert tracker.completed is False
    assert tracker.max_progress < metadata.total_length_px

    tracker.advance(centers[0], centers[1], tick=len(centers) + 2)

    assert tracker.completed is True
    assert tracker.lap_ticks == len(centers) + 2
    assert tracker.checkpoints_completed == len(centers) + 1
    assert tracker.max_progress == metadata.total_length_px
