from __future__ import annotations

import random
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from GA.genetic import (
    mutateOneBiasesGene,
    mutateOneWeightGene,
    uniformCrossOverBiases,
    uniformCrossOverWeights,
)
from shared.contracts import DEFAULT_EVOLUTION_SEED, RuntimeSettings


GENERATION_DURATION_SECONDS = 40.0


def _nested_tuple(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_nested_tuple(item) for item in value)
    return value


def create_evolution_rngs(
    seed: int,
    mlp_init_rng_state: dict[str, Any] | None = None,
    mutation_rng_state: tuple[Any, ...] | list[Any] | None = None,
) -> tuple[np.random.Generator, random.Random]:
    """Create evolution RNGs, optionally continuing from a saved state."""
    mlp_init_rng = np.random.default_rng(seed)
    if mlp_init_rng_state is not None:
        mlp_init_rng.bit_generator.state = deepcopy(mlp_init_rng_state)

    mutation_rng = random.Random(seed)
    if mutation_rng_state is not None:
        mutation_rng.setstate(_nested_tuple(mutation_rng_state))
    return mlp_init_rng, mutation_rng


@dataclass
class TrainingSession:
    population_size: int
    mutation_rate: int
    evolution_seed: int = DEFAULT_EVOLUTION_SEED
    generation: int = 1
    alive_count: int = 0
    selected_cars: list[Any] = field(default_factory=list)
    track_index: int = 1
    show_sensor_lines: bool = False
    show_player: bool = True
    show_debug_overlay: bool = True
    mlp_init_rng: np.random.Generator = field(init=False, repr=False)
    mutation_rng: random.Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._reset_evolution_rngs()

    @classmethod
    def from_settings(cls, settings: RuntimeSettings) -> "TrainingSession":
        return cls(
            population_size=settings.population_size,
            mutation_rate=settings.mutation_rate,
            evolution_seed=settings.evolution_seed,
            alive_count=settings.population_size,
            show_player=settings.show_player,
            show_debug_overlay=settings.show_debug_overlay,
        )

    def toggle_selected_car(self, car: Any) -> None:
        if car in self.selected_cars:
            self.selected_cars.remove(car)
            return
        if len(self.selected_cars) < 2:
            self.selected_cars.append(car)

    def clear_selection(self) -> None:
        self.selected_cars.clear()

    def reset_generation(self) -> None:
        self.generation = 1
        self.alive_count = self.population_size
        self.clear_selection()
        self._reset_evolution_rngs()

    def restart_with_seed(self, seed: int) -> None:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise TypeError("seed must be an integer")
        if seed < 0:
            raise ValueError("seed cannot be negative")
        self.evolution_seed = seed
        self.reset_generation()

    def _reset_evolution_rngs(self) -> None:
        self.mlp_init_rng, self.mutation_rng = create_evolution_rngs(
            self.evolution_seed
        )

    def snapshot_evolution_rngs(
        self,
    ) -> tuple[dict[str, Any], tuple[Any, ...]]:
        return (
            deepcopy(dict(self.mlp_init_rng.bit_generator.state)),
            self.mutation_rng.getstate(),
        )

    def begin_next_generation(self) -> None:
        self.generation += 1
        self.alive_count = self.population_size
        self.clear_selection()

    def should_end_generation(self, elapsed_seconds: float) -> bool:
        if elapsed_seconds < 0:
            raise ValueError("elapsed_seconds cannot be negative")
        return (
            elapsed_seconds >= GENERATION_DURATION_SECONDS
            or self.alive_count <= 0
        )

    def mark_collision(self, car: Any) -> bool:
        if getattr(car, "yaReste", False):
            return False
        car.yaReste = True
        self.alive_count = max(0, self.alive_count - 1)
        return True

    def breed_population(
        self,
        population: list[Any],
        aux_car: Any,
        car_factory: Any,
        layer_sizes: list[int],
        assets: Any,
    ) -> list[Any]:
        if len(self.selected_cars) != 2:
            return population

        parent1, parent2 = self.selected_cars
        self.begin_next_generation()
        next_population = [
            car_factory(
                layer_sizes,
                mlp_init_seed=self.evolution_seed,
                mlp_init_rng=self.mlp_init_rng,
            )
            for _ in range(self.population_size)
        ]

        for index in range(0, self.population_size - 2, 2):
            uniformCrossOverWeights(
                parent1,
                parent2,
                next_population[index],
                next_population[index + 1],
            )
            uniformCrossOverBiases(
                parent1,
                parent2,
                next_population[index],
                next_population[index + 1],
            )

        next_population[self.population_size - 2] = parent1
        next_population[self.population_size - 1] = parent2

        next_population[self.population_size - 2].car_image = assets.green_small_car
        next_population[self.population_size - 1].car_image = assets.green_small_car

        for champion in next_population[self.population_size - 2 :]:
            champion.reset_state(car_image=assets.green_small_car)

        for index in range(self.population_size - 2):
            for _ in range(self.mutation_rate):
                mutateOneWeightGene(
                    next_population[index], aux_car, self.mutation_rng
                )
                mutateOneWeightGene(
                    aux_car, next_population[index], self.mutation_rng
                )
                mutateOneBiasesGene(
                    next_population[index], aux_car, self.mutation_rng
                )
                mutateOneBiasesGene(
                    aux_car, next_population[index], self.mutation_rng
                )

        self.clear_selection()
        return next_population
