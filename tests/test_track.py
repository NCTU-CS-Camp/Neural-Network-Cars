from pathlib import Path

import pytest

from game_engine.backend.track import TrackGeometry


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_loads_ordered_centerline_from_tile_connections() -> None:
    track = TrackGeometry.from_json(
        PROJECT_ROOT / "maps/train_maps/train_easy.json",
        default_half_width=66.0,
    )

    assert len(track.centerline) == 26
    assert track.total_length == pytest.approx(3796.0)
    assert track.centerline[:2] == ((143.0, 450.0), (143.0, 304.0))
    assert track.centerline[-1] == (143.0, 596.0)


def test_projection_exposes_progress_offset_and_project_heading() -> None:
    track = TrackGeometry.from_json(
        PROJECT_ROOT / "maps/train_maps/train_easy.json",
        default_half_width=66.0,
    )

    projection = track.project((153.0, 400.0))

    assert projection.progress == pytest.approx(50.0)
    assert projection.center_offset == pytest.approx(10.0)
    assert projection.target_heading == pytest.approx(180.0)


def test_track_boundary_uses_verified_asset_half_width() -> None:
    track = TrackGeometry.from_json(
        PROJECT_ROOT / "maps/train_maps/train_easy.json",
        default_half_width=66.0,
    )

    assert track.contains((209.0, 400.0))
    assert not track.contains((209.01, 400.0))
