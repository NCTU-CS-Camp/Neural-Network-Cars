import json

import numpy as np

from game_engine.backend.car import Car
from game_engine.backend.training_session import TrainingSession
from game_engine.frontend.screens import (
    SUBMISSION_POPULATION_SIZE,
    VALIDATION_POPULATION_SIZE,
    _build_candidates,
)
from shared.contracts import TrainingRecord


LAYER_SIZES = [2, 3, 1]


def test_submission_and_validation_population_sizes() -> None:
    assert SUBMISSION_POPULATION_SIZE == 100
    assert VALIDATION_POPULATION_SIZE == 100
    candidates = _build_candidates(
        Car(LAYER_SIZES),
        Car(LAYER_SIZES),
        LAYER_SIZES,
        mutation_rate=0,
    )

    assert len(candidates) == 100


def test_submission_candidates_follow_parent_seed_reproducibly() -> None:
    first_parent_a = Car(LAYER_SIZES, mlp_init_seed=123)
    first_parent_b = Car(LAYER_SIZES, mlp_init_seed=456)
    second_parent_a = Car(LAYER_SIZES, mlp_init_seed=123)
    second_parent_b = Car(LAYER_SIZES, mlp_init_seed=456)

    first_candidates = _build_candidates(
        first_parent_a, first_parent_b, LAYER_SIZES, mutation_rate=2, total=4
    )
    second_candidates = _build_candidates(
        second_parent_a, second_parent_b, LAYER_SIZES, mutation_rate=2, total=4
    )

    assert all(candidate.mlp_init_seed == 123 for candidate in first_candidates)
    for first, second in zip(first_candidates, second_candidates, strict=True):
        for first_layer, second_layer in zip(
            first.weights + first.biases,
            second.weights + second.biases,
            strict=True,
        ):
            np.testing.assert_array_equal(first_layer, second_layer)


def test_legacy_training_record_defaults_seed_to_3057() -> None:
    record = TrainingRecord.from_dict(
        {
            "record_id": "legacy",
            "record_name": "Legacy record",
            "saved_at": "2026-01-01T00:00:00+00:00",
            "group_id": "1",
            "username": "player",
            "layer_sizes": LAYER_SIZES,
            "parent_a_weights": [],
            "parent_a_biases": [],
            "parent_b_weights": [],
            "parent_b_biases": [],
            "fitness_config": {},
            "map_difficulty": 1,
        }
    )

    assert record.mlp_init_seed == 3057
    assert record.mlp_init_rng_state is None
    assert record.mutation_rng_state is None
    assert record.to_dict()["mlp_init_seed"] == 3057


def test_submission_continues_json_round_tripped_training_rng_states() -> None:
    session = TrainingSession(
        population_size=4,
        mutation_rate=2,
        evolution_seed=123,
    )
    session.mlp_init_rng.standard_normal(280)
    for _ in range(8):
        session.mutation_rng.randint(0, 9)
        session.mutation_rng.uniform(0.8, 1.2)
    mlp_state, mutation_state = session.snapshot_evolution_rngs()
    serialized_states = json.loads(
        json.dumps(
            {
                "mlp": mlp_state,
                "mutation": mutation_state,
            }
        )
    )
    parent_a = Car(LAYER_SIZES, mlp_init_seed=123)
    parent_b = Car(LAYER_SIZES, mlp_init_seed=456)

    first_candidates = _build_candidates(
        parent_a,
        parent_b,
        LAYER_SIZES,
        mutation_rate=2,
        total=4,
        mlp_init_rng_state=serialized_states["mlp"],
        mutation_rng_state=serialized_states["mutation"],
    )
    second_candidates = _build_candidates(
        parent_a,
        parent_b,
        LAYER_SIZES,
        mutation_rate=2,
        total=4,
        mlp_init_rng_state=serialized_states["mlp"],
        mutation_rng_state=serialized_states["mutation"],
    )

    for first, second in zip(first_candidates, second_candidates, strict=True):
        for first_layer, second_layer in zip(
            first.weights + first.biases,
            second.weights + second.biases,
            strict=True,
        ):
            np.testing.assert_array_equal(first_layer, second_layer)
