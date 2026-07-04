from __future__ import annotations

import numpy as np

from game_engine.backend.car import Car
from game_engine.backend.training_session import create_evolution_rngs
from shared.contracts import RuntimeSettings


def population(seed: int, count: int) -> list[Car]:
    rng, _ = create_evolution_rngs(seed)
    return [
        Car([6, 6, 4], mlp_init_seed=seed, mlp_init_rng=rng)
        for _ in range(count)
    ]


def test_same_nn_seed_recreates_identical_initial_population() -> None:
    first = population(3057, 4)
    second = population(3057, 4)

    for first_car, second_car in zip(first, second):
        for first_weights, second_weights in zip(
            first_car.weights,
            second_car.weights,
        ):
            np.testing.assert_array_equal(first_weights, second_weights)
        for first_biases, second_biases in zip(
            first_car.biases,
            second_car.biases,
        ):
            np.testing.assert_array_equal(first_biases, second_biases)


def test_different_nn_seed_changes_initial_weights() -> None:
    first = population(3057, 1)[0]
    second = population(3058, 1)[0]

    assert not np.array_equal(first.weights[0], second.weights[0])


def test_track_seed_does_not_override_evolution_seed() -> None:
    settings = RuntimeSettings.from_dict({"track_seed": 3057})

    assert settings.track_seed == 3057
    assert settings.evolution_seed == 3057
