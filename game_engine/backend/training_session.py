from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from GA.genetic import (
    mutateOneBiasesGene,
    mutateOneWeightGene,
    uniformCrossOverBiases,
    uniformCrossOverWeights,
)
from shared.contracts import RuntimeSettings


@dataclass
class TrainingSession:
    population_size: int
    mutation_rate: int
    fitness_strategy: str
    generation: int = 1
    alive_count: int = 0
    selected_cars: list[Any] = field(default_factory=list)
    track_index: int = 1
    show_sensor_lines: bool = True
    show_player: bool = True
    show_debug_overlay: bool = True

    @classmethod
    def from_settings(cls, settings: RuntimeSettings) -> "TrainingSession":
        return cls(
            population_size=settings.population_size,
            mutation_rate=settings.mutation_rate,
            fitness_strategy=settings.fitness_strategy,
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

    def begin_next_generation(self) -> None:
        self.generation += 1
        self.alive_count = self.population_size
        self.clear_selection()

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

        self.begin_next_generation()
        next_population = [car_factory(layer_sizes) for _ in range(self.population_size)]

        for index in range(0, self.population_size - 2, 2):
            uniformCrossOverWeights(
                self.selected_cars[0],
                self.selected_cars[1],
                next_population[index],
                next_population[index + 1],
            )
            uniformCrossOverBiases(
                self.selected_cars[0],
                self.selected_cars[1],
                next_population[index],
                next_population[index + 1],
            )

        next_population[self.population_size - 2] = self.selected_cars[0]
        next_population[self.population_size - 1] = self.selected_cars[1]

        next_population[self.population_size - 2].car_image = assets.green_small_car
        next_population[self.population_size - 1].car_image = assets.green_small_car

        for champion in next_population[self.population_size - 2 :]:
            champion.resetPosition()
            champion.collided = False
            champion.yaReste = False
            champion.score = 0

        for index in range(self.population_size - 2):
            for _ in range(self.mutation_rate):
                mutateOneWeightGene(next_population[index], aux_car)
                mutateOneWeightGene(aux_car, next_population[index])
                mutateOneBiasesGene(next_population[index], aux_car)
                mutateOneBiasesGene(aux_car, next_population[index])

        self.clear_selection()
        return next_population
