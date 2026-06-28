import random

import numpy as np

from GA.genetic import mutateOneBiasesGene, mutateOneWeightGene
from game_engine.backend.car import Car


def _assert_same_parameters(first: Car, second: Car) -> None:
    for first_layer, second_layer in zip(
        first.weights + first.biases,
        second.weights + second.biases,
        strict=True,
    ):
        np.testing.assert_array_equal(first_layer, second_layer)


def test_mutations_are_reproducible_with_attempt_rng() -> None:
    parent = Car([2, 3, 1], mlp_init_seed=10)
    first_child = Car([2, 3, 1], mlp_init_seed=20)
    second_child = Car([2, 3, 1], mlp_init_seed=30)
    first_rng = random.Random(3057)
    second_rng = random.Random(3057)

    mutateOneWeightGene(parent, first_child, first_rng)
    mutateOneBiasesGene(first_child, first_child, first_rng)
    mutateOneWeightGene(parent, second_child, second_rng)
    mutateOneBiasesGene(second_child, second_child, second_rng)

    _assert_same_parameters(first_child, second_child)
