from types import SimpleNamespace

import pytest

from GA.fitness import beginner_mix, select_best_cars
from game_engine.backend.simulator import FrameTelemetry
from shared.contracts import FitnessConfig


def _example_telemetry(**overrides: object) -> FrameTelemetry:
    values = {
        "velocity": 8.0,
        "progress_delta": 3.0,
        "progress_ratio": 0.25,
        "center_offset": 10.0,
        "track_half_width": 42.0,
        "heading_delta": 30.0,
        "heading_alignment": 3**0.5 / 2.0,
        "min_clearance": 45.0,
        "is_stalled": False,
        "is_spinning": False,
        "is_wrong_way": False,
        "time_elapsed": 5.0,
        "collided": False,
        "finished_now": False,
    }
    values.update(overrides)
    return FrameTelemetry(**values)  # type: ignore[arg-type]


def _example_config() -> FitnessConfig:
    return FitnessConfig(
        weights={
            "progress": 60,
            "speed": 40,
            "alignment": 0,
            "safety": 50,
            "centered": 20,
            "stall": 50,
            "spin": 40,
            "wrong_way": 0,
            "time": 30,
            "crash": 70,
        }
    )


def test_beginner_mix_matches_documented_numeric_example() -> None:
    result = beginner_mix(_example_telemetry(), _example_config())

    assert result.total == pytest.approx(22.2297619048)
    assert result.rewards["speed"] == pytest.approx(3.2)
    assert result.rewards["progress"] == pytest.approx(18.0)
    assert result.builtin_progress == pytest.approx(0.125)


def test_crash_and_finish_are_applied_to_the_current_frame() -> None:
    crash = beginner_mix(
        _example_telemetry(collided=True),
        _example_config(),
    )
    finish = beginner_mix(
        _example_telemetry(finished_now=True),
        _example_config(),
    )

    assert crash.total == pytest.approx(-677.7702380952)
    assert finish.total == pytest.approx(10022.2297619048)


def test_reward_is_clamped_but_penalty_has_no_upper_limit() -> None:
    config = FitnessConfig(weights={"speed": 150, "crash": 150})
    result = beginner_mix(
        _example_telemetry(collided=True),
        config,
    )

    assert result.rewards["speed"] == pytest.approx(8.0)
    assert result.penalties["crash"] == pytest.approx(1500.0)


def test_all_boolean_penalties_use_documented_per_frame_scales() -> None:
    config = FitnessConfig(
        weights={
            "stall": 100,
            "spin": 50,
            "wrong_way": 25,
            "time": 100,
            "crash": 100,
        }
    )
    result = beginner_mix(
        _example_telemetry(
            is_stalled=True,
            is_spinning=True,
            is_wrong_way=True,
            collided=True,
        ),
        config,
    )

    assert result.penalties == pytest.approx(
        {
            "stall": 10.0,
            "spin": 5.0,
            "wrong_way": 2.5,
            "time": 0.5,
            "crash": 1000.0,
        }
    )


def test_alignment_reward_clamps_negative_alignment_to_zero() -> None:
    config = FitnessConfig(weights={"alignment": 100})

    result = beginner_mix(
        _example_telemetry(heading_alignment=-1.0),
        config,
    )

    assert result.rewards["alignment"] == 0.0


def test_select_best_cars_returns_highest_accumulated_scores() -> None:
    cars = [
        SimpleNamespace(fitness_score=-5.0),
        SimpleNamespace(fitness_score=30.0),
        SimpleNamespace(fitness_score=12.0),
    ]

    selected = select_best_cars(cars, _example_config(), count=2)

    assert [car.fitness_score for car in selected] == [30.0, 12.0]


def test_legacy_fitness_keys_are_rejected() -> None:
    with pytest.raises(ValueError, match="progress_score"):
        beginner_mix(
            _example_telemetry(),
            FitnessConfig(weights={"progress_score": 50}),
        )
