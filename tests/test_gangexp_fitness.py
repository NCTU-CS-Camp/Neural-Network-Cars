from __future__ import annotations

import pytest

from GA.fitness import (
    B_CRASH,
    FINISH_BONUS,
    BeginnerMix,
    StepContext,
    build_beginner_mix,
)
from shared.contracts import FitnessConfig


def context(**overrides: object) -> StepContext:
    values = {
        "velocity": 0.0,
        "progress_delta": 0.0,
        "reverse_progress_delta": 0.0,
        "progress_ratio": 0.0,
        "center_offset": 0.0,
        "normalized_center_offset": 0.0,
        "heading_alignment": 1.0,
        "front_clearance": 100.0,
        "min_clearance": 100.0,
        "side_clearance_balance": 0.0,
        "turn_amount": 0.0,
        "collided": False,
        "finished": False,
        "is_stalled": False,
        "is_spinning": False,
        "frame": 30,
        "time_elapsed": 1.0,
    }
    values.update(overrides)
    return StepContext(**values)  # type: ignore[arg-type]


def test_engine_builds_beginner_mix_from_ten_values() -> None:
    config = FitnessConfig.from_weights(
        {
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

    strategy = build_beginner_mix(config)

    assert isinstance(strategy, BeginnerMix)
    assert strategy.score_step(
        context(velocity=10.0, progress_delta=1.0)
    ) == pytest.approx(10.0)


def test_wrong_way_penalty_uses_heading_or_reverse_progress() -> None:
    strategy = BeginnerMix()
    strategy.configure({"penalties": {"wrong_way": 100}})

    assert strategy.score_step(
        context(heading_alignment=-0.5)
    ) == pytest.approx(-15.0)
    assert strategy.score_step(
        context(reverse_progress_delta=5.0)
    ) == pytest.approx(-15.0)


def test_crash_and_finish_keep_gangexp_constants() -> None:
    strategy = BeginnerMix()
    strategy.configure({"penalties": {"crash": 100}})

    assert strategy.score_step(context(collided=True)) == -B_CRASH
    assert strategy.score_step(context(finished=True)) == FINISH_BONUS
