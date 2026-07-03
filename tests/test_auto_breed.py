from __future__ import annotations

from types import SimpleNamespace

from GA.fitness import select_top_k_cars
from game_engine.backend.car import Car
from game_engine.backend.training_session import TrainingSession
from game_engine.frontend.app import (
    AUTO_BREED_FRAMES,
    AUTO_BREED_SECONDS,
    advance_generation_countdown,
)
from shared.contracts import FitnessConfig


def test_auto_breed_countdown_reaches_zero_after_ten_seconds() -> None:
    frames_remaining = AUTO_BREED_FRAMES

    for _ in range(AUTO_BREED_FRAMES - 1):
        frames_remaining, time_limit_reached = advance_generation_countdown(
            frames_remaining
        )

    assert AUTO_BREED_SECONDS == 10
    assert frames_remaining == 1
    assert not time_limit_reached

    frames_remaining, time_limit_reached = advance_generation_countdown(
        frames_remaining
    )

    assert frames_remaining == 0
    assert time_limit_reached


def test_parent_selection_uses_accumulated_beginner_mix_fitness() -> None:
    cars = [
        SimpleNamespace(fitness_score=10.0),
        SimpleNamespace(fitness_score=90.0),
        SimpleNamespace(fitness_score=30.0),
        SimpleNamespace(fitness_score=80.0),
    ]

    parents = select_top_k_cars(cars, FitnessConfig(), k=2)

    assert [car.fitness_score for car in parents] == [90.0, 80.0]


def test_breed_keeps_two_elite_parents_and_advances_generation() -> None:
    session = TrainingSession(
        population_size=4,
        mutation_rate=0,
        fitness_strategy="beginner_mix",
    )
    population = [Car([2, 2]) for _ in range(4)]
    parent_a = population[1]
    parent_b = population[3]
    session.selected_cars = [parent_a, parent_b]
    assets = SimpleNamespace(green_small_car=object())

    next_population = session.breed_population(
        population=population,
        aux_car=Car([2, 2]),
        car_factory=Car,
        layer_sizes=[2, 2],
        assets=assets,
    )

    assert len(next_population) == 4
    assert next_population[-2:] == [parent_a, parent_b]
    assert session.generation == 2
    assert session.selected_cars == []
