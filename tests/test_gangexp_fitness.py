from __future__ import annotations

import pytest

from GA.fitness import FitnessStrategy
from game_engine.backend.simulator import FrameTelemetry
from shared.contracts import FitnessConfig


def telemetry(**overrides: object) -> FrameTelemetry:
    values = {
        "velocity": 0.0,
        "progress_delta": 0.0,
        "progress_ratio": 0.0,
        "center_offset": 0.0,
        "track_half_width": 100.0,
        "heading_delta": 0.0,
        "heading_alignment": 1.0,
        "min_clearance": 100.0,
        "collided": False,
        "finished_now": False,
        "is_stalled": False,
        "is_spinning": False,
        "is_wrong_way": False,
        "time_elapsed": 1.0,
    }
    values.update(overrides)
    return FrameTelemetry(**values)  # type: ignore[arg-type]


def test_engine_builds_beginner_mix_from_ten_values() -> None:
    config = FitnessConfig(
        weights={
            "speed": 40,
            "progress": 60,
            "centered": 0,
            "alignment": 0,
            "safety": 0,
            "stall": 0,
            "spin": 0,
            "wrong_way": 0,
            "time": 0,
            "crash": 0,
        }
    )

    strategy = FitnessStrategy(name="custom", config=config)

    assert strategy.score_frame(
        telemetry(velocity=10.0, progress_delta=1.0)
    ) == pytest.approx(10.0)


def test_wrong_way_penalty_uses_heading_or_reverse_progress() -> None:
    strategy = FitnessStrategy(
        name="wrong-way",
        config=FitnessConfig(wrong_way=100),
    )

    assert strategy.score_frame(
        telemetry(heading_alignment=-0.5, is_wrong_way=True)
    ) == pytest.approx(-10.0)


def test_crash_and_finish_keep_gangexp_constants() -> None:
    strategy = FitnessStrategy(name="events", config=FitnessConfig(crash=100))

    assert strategy.score_frame(telemetry(collided=True)) == -1000.0
    assert strategy.score_frame(telemetry(finished_now=True)) == 10000.0
