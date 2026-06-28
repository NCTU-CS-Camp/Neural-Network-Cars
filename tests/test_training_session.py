from types import SimpleNamespace

import pytest

from game_engine.backend.training_session import (
    GENERATION_DURATION_SECONDS,
    TrainingSession,
)


def _session(*, alive_count: int = 2) -> TrainingSession:
    return TrainingSession(
        population_size=2,
        mutation_rate=0,
        alive_count=alive_count,
    )


def test_generation_ends_at_time_limit() -> None:
    session = _session()

    assert not session.should_end_generation(GENERATION_DURATION_SECONDS - 0.01)
    assert session.should_end_generation(GENERATION_DURATION_SECONDS)


def test_generation_ends_when_all_cars_have_crashed() -> None:
    session = _session(alive_count=1)
    car = SimpleNamespace(yaReste=False)

    session.mark_collision(car)

    assert session.alive_count == 0
    assert session.should_end_generation(0.0)


def test_generation_elapsed_time_cannot_be_negative() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        _session().should_end_generation(-0.01)


def test_reset_generation_replays_evolution_random_streams() -> None:
    session = TrainingSession(
        population_size=2,
        mutation_rate=1,
        evolution_seed=3057,
    )
    first_mlp_values = session.mlp_init_rng.standard_normal(4)
    first_mutation_values = (
        session.mutation_rng.randint(0, 100),
        session.mutation_rng.uniform(0.8, 1.2),
    )

    session.reset_generation()

    assert session.mlp_init_rng.standard_normal(4) == pytest.approx(
        first_mlp_values
    )
    assert (
        session.mutation_rng.randint(0, 100),
        session.mutation_rng.uniform(0.8, 1.2),
    ) == pytest.approx(first_mutation_values)
