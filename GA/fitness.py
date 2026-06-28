from __future__ import annotations

from dataclasses import dataclass

from game_engine.backend.simulator import FrameTelemetry
from shared.contracts import FitnessConfig


REWARD_NAMES = ("speed", "progress", "centered", "alignment", "safety")
PENALTY_NAMES = ("stall", "spin", "wrong_way", "time", "crash")
FITNESS_NAMES = frozenset(FitnessConfig.weight_names())


@dataclass(frozen=True, slots=True)
class FitnessBreakdown:
    rewards: dict[str, float]
    penalties: dict[str, float]
    builtin_progress: float
    finish_bonus: float
    total: float


def validate_fitness_config(fitness_config: FitnessConfig) -> None:
    for name in FITNESS_NAMES:
        value = getattr(fitness_config, name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"Fitness weight {name!r} must be numeric")


def _reward_weight(value: int | float) -> float:
    return min(100.0, max(0.0, float(value))) / 100.0


def _penalty_weight(value: int | float) -> float:
    return max(0.0, float(value)) / 100.0


def beginner_mix(
    telemetry: FrameTelemetry,
    fitness_config: FitnessConfig,
) -> FitnessBreakdown:
    validate_fitness_config(fitness_config)

    centered_factor = min(
        1.0,
        max(
            0.0,
            1.0 - (telemetry.center_offset / telemetry.track_half_width),
        ),
    )
    alignment_factor = min(1.0, max(0.0, telemetry.heading_alignment))
    safety_factor = min(1.0, max(0.0, telemetry.min_clearance / 90.0))

    rewards = {
        "speed": (
            _reward_weight(fitness_config.speed)
            * 1.0
            * max(0.0, telemetry.velocity)
        ),
        "progress": (
            _reward_weight(fitness_config.progress)
            * 10.0
            * max(0.0, telemetry.progress_delta)
        ),
        "centered": (
            _reward_weight(fitness_config.centered)
            * 2.0
            * centered_factor
        ),
        "alignment": (
            _reward_weight(fitness_config.alignment)
            * 3.0
            * alignment_factor
        ),
        "safety": (
            _reward_weight(fitness_config.safety)
            * 3.0
            * safety_factor
        ),
    }
    penalties = {
        "stall": (
            _penalty_weight(fitness_config.stall)
            * 10.0
            * float(telemetry.is_stalled)
        ),
        "spin": (
            _penalty_weight(fitness_config.spin)
            * 10.0
            * float(telemetry.is_spinning)
        ),
        "wrong_way": (
            _penalty_weight(fitness_config.wrong_way)
            * 10.0
            * float(telemetry.is_wrong_way)
        ),
        "time": (
            _penalty_weight(fitness_config.time)
            * 0.1
            * telemetry.time_elapsed
        ),
        "crash": (
            _penalty_weight(fitness_config.crash)
            * 1000.0
            * float(telemetry.collided)
        ),
    }
    builtin_progress = min(1.0, max(0.0, telemetry.progress_ratio)) * 0.5
    finish_bonus = 10000.0 if telemetry.finished_now else 0.0
    total = (
        sum(rewards.values())
        + builtin_progress
        + finish_bonus
        - sum(penalties.values())
    )
    return FitnessBreakdown(
        rewards=rewards,
        penalties=penalties,
        builtin_progress=builtin_progress,
        finish_bonus=finish_bonus,
        total=total,
    )


def score_with_config(car: object, fitness_config: FitnessConfig) -> float:
    validate_fitness_config(fitness_config)
    return float(getattr(car, "fitness_score", 0.0))


def score_population(
    population: list[object],
    fitness_config: FitnessConfig,
) -> list[float]:
    return [score_with_config(car, fitness_config) for car in population]


def select_best_cars(
    population: list[object],
    fitness_config: FitnessConfig,
    *,
    count: int,
) -> list[object]:
    if count < 1:
        raise ValueError("count must be positive")
    if len(population) < count:
        raise ValueError("population does not contain enough cars")
    validate_fitness_config(fitness_config)
    return sorted(
        population,
        key=lambda car: float(getattr(car, "fitness_score", 0.0)),
        reverse=True,
    )[:count]


def select_best_car(
    population: list[object],
    fitness_config: FitnessConfig,
) -> object:
    return select_best_cars(population, fitness_config, count=1)[0]
