from __future__ import annotations

from typing import Callable

from shared.contracts import FitnessConfig


FitnessStrategy = Callable[[object], float]


def baseline_distance(car: object) -> float:
    return float(getattr(car, "score", 0.0))


def progress_speed(car: object) -> float:
    score = float(getattr(car, "score", 0.0))
    velocity = float(getattr(car, "velocity", 0.0))
    collided = bool(getattr(car, "collided", False))
    return score + (velocity * 5.0) - (25.0 if collided else 0.0)


def checkpoint_progress(car: object) -> float:
    score = float(getattr(car, "score", 0.0))
    velocity = float(getattr(car, "velocity", 0.0))
    d1 = float(getattr(car, "d1", 0.0))
    d2 = float(getattr(car, "d2", 0.0))
    d3 = float(getattr(car, "d3", 0.0))
    sensor_balance = min(d1, d2 + d3)
    stalled = velocity < 0.5
    return score + sensor_balance - (50.0 if stalled else 0.0)


FITNESS_STRATEGIES: dict[str, FitnessStrategy] = {
    "baseline_distance": baseline_distance,
    "progress_speed": progress_speed,
    "checkpoint_progress": checkpoint_progress,
}


def get_fitness_strategy(name: str) -> FitnessStrategy:
    return FITNESS_STRATEGIES.get(name, baseline_distance)


def score_population(population: list[object], strategy_name: str) -> list[float]:
    strategy = get_fitness_strategy(strategy_name)
    return [strategy(car) for car in population]


def score_with_config(car: object, fitness_config: FitnessConfig) -> float:
    return sum(
        weight * get_fitness_strategy(name)(car)
        for name, weight in fitness_config.weights.items()
    )


def select_best_car(population: list[object], fitness_config: FitnessConfig) -> object:
    return max(population, key=lambda car: score_with_config(car, fitness_config))


def select_top_k_cars(
    population: list[object], fitness_config: FitnessConfig, k: int = 2
) -> list[object]:
    return sorted(population, key=lambda car: score_with_config(car, fitness_config), reverse=True)[:k]

