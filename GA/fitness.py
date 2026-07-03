from __future__ import annotations

from dataclasses import dataclass

from game_engine.backend.simulator import FrameTelemetry
from shared.contracts import FitnessConfig


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


@dataclass(frozen=True, slots=True)
class FitnessStrategy:
    name: str
    config: FitnessConfig

    def copy(self) -> "FitnessStrategy":
        return type(self)(
            name=self.name,
            config=self.config.copy(),
        )

    def score_frame(self, telemetry: FrameTelemetry) -> float:
        return self.explain_frame(telemetry).total

    def explain_frame(self, telemetry: FrameTelemetry) -> FitnessBreakdown:
        return calculate_score(telemetry, self.config)


def calculate_score(
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


# Preset objects. Call copy() before changing config values for a user session.
BeginnerMix = FitnessStrategy(
    name="BeginnerMix",
    config=FitnessConfig(
        speed=25,
        progress=10,
        centered=35,
        alignment=40,
        safety=25,
        stall=20,
        spin=15,
        wrong_way=40,
        time=5,
        crash=50,
    ),
)

ProgressFirst = FitnessStrategy(
    name="ProgressFirst",
    config=FitnessConfig(
        speed=30,
        progress=20,
        centered=10,
        alignment=25,
        safety=10,
        stall=15,
        spin=10,
        wrong_way=35,
        time=3,
        crash=35,
    ),
)

SafeFinish = FitnessStrategy(
    name="SafeFinish",
    config=FitnessConfig(
        speed=15,
        progress=10,
        centered=60,
        alignment=60,
        safety=50,
        stall=20,
        spin=25,
        wrong_way=70,
        time=5,
        crash=90,
    ),
)

Equal50Debug = FitnessStrategy(
    name="Equal50Debug",
    config=FitnessConfig(weights={name: 50 for name in FitnessConfig.weight_names()}),
)

FITNESS_STRATEGIES: tuple[FitnessStrategy, ...] = (
    BeginnerMix,
    ProgressFirst,
    SafeFinish,
    Equal50Debug,
)


def fitness_strategy_names() -> tuple[str, ...]:
    return tuple(strategy.name for strategy in FITNESS_STRATEGIES)


def get_fitness_strategy(name: str) -> FitnessStrategy:
    for strategy in FITNESS_STRATEGIES:
        if strategy.name == name:
            return strategy.copy()
    raise ValueError(f"Unknown fitness strategy: {name}")


def score_with_config(car: object, fitness_config: FitnessConfig) -> float:
    validate_fitness_config(fitness_config)
    return float(getattr(car, "fitness_score", 0.0))


def select_best_cars(
    population: list[object],
    *,
    count: int,
) -> list[object]:
    if count < 1:
        raise ValueError("count must be positive")
    if len(population) < count:
        raise ValueError("population does not contain enough cars")
    return sorted(
        population,
        key=lambda car: float(getattr(car, "fitness_score", 0.0)),
        reverse=True,
    )[:count]
