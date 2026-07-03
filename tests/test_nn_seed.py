from __future__ import annotations

import numpy as np

from game_engine.backend.car import create_seeded_population
from shared.contracts import RuntimeSettings


def test_same_nn_seed_recreates_identical_initial_population() -> None:
    first = create_seeded_population([6, 6, 4], 4, seed=3057)
    second = create_seeded_population([6, 6, 4], 4, seed=3057)

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
    first = create_seeded_population([6, 6, 4], 1, seed=3057)[0]
    second = create_seeded_population([6, 6, 4], 1, seed=3058)[0]

    assert not np.array_equal(first.weights[0], second.weights[0])


def test_legacy_custom_seed_migrates_to_nn_seed() -> None:
    settings = RuntimeSettings.from_dict({"track_seed": 3057})

    assert settings.track_seed == 3057
    assert settings.nn_seed == 3057
