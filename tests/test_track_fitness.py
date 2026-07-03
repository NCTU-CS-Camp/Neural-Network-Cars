from __future__ import annotations

from dataclasses import dataclass

import pytest

from GA.fitness import BeginnerMix
from game_engine.backend.fitness_tracker import FitnessTracker
from game_engine.backend.settings import TRAINING_MAP_METADATA
from game_engine.backend.track_geometry import (
    TrackGeometry,
    load_track_geometry,
)


@dataclass
class FakeCar:
    x: float
    y: float
    angle: float
    velocity: float = 1.0
    d1: float = 50.0
    d2: float = 50.0
    d3: float = 50.0
    d4: float = 50.0
    d5: float = 50.0
    fitness_score: float = 0.0
    finished: bool = False


def test_manual_training_maps_build_ordered_track_geometry() -> None:
    for metadata_path in TRAINING_MAP_METADATA.values():
        track = load_track_geometry(metadata_path)

        assert len(track.polyline) > 2
        assert track.total_length > 0
        assert track.project(track.start_position)[0] == pytest.approx(0.0)
        assert track.is_on_track(track.start_position)


def test_tracker_supplies_real_progress_to_gangexp_strategy() -> None:
    track = TrackGeometry.from_route_cells([(0, 1), (0, 0)])
    strategy = BeginnerMix()
    strategy.configure({"rewards": {"progress": 100}})
    car = FakeCar(*track.start_position, angle=track.start_angle)
    tracker = FitnessTracker.for_car(
        car,
        track=track,
        strategy=strategy,
        fps=30,
    )
    car.y -= 5

    result = tracker.advance(
        car,
        previous_angle=track.start_angle,
        collided=False,
    )

    assert result.progress_delta == pytest.approx(5.0)
    assert result.reverse_progress_delta == 0.0
    assert tracker.total_fitness > 0.0
    assert car.fitness_score == tracker.total_fitness


def test_tracker_detects_reverse_progress() -> None:
    track = TrackGeometry.from_route_cells([(0, 1), (0, 0)])
    strategy = BeginnerMix()
    strategy.configure({"penalties": {"wrong_way": 100}})
    car = FakeCar(*track.start_position, angle=track.start_angle)
    car.y -= 10
    tracker = FitnessTracker.for_car(
        car,
        track=track,
        strategy=strategy,
        fps=30,
    )
    car.y += 5

    result = tracker.advance(
        car,
        previous_angle=track.start_angle,
        collided=False,
    )

    assert result.progress_delta == 0.0
    assert result.reverse_progress_delta == pytest.approx(5.0)
    assert tracker.total_fitness < 0.0


def test_tracker_stops_at_fixed_frame_limit() -> None:
    track = TrackGeometry.from_route_cells([(0, 1), (0, 0)])
    car = FakeCar(*track.start_position, angle=track.start_angle)
    tracker = FitnessTracker.for_car(
        car,
        track=track,
        strategy=BeginnerMix(),
        fps=30,
        max_frames=1,
    )

    tracker.advance(
        car,
        previous_angle=track.start_angle,
        collided=False,
    )

    assert tracker.timed_out is True
    assert tracker.stopped is True
