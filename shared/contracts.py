from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class RuntimeSettings:
    nickname: str = "player1"
    fps: int = 30
    population_size: int = 50
    mutation_rate: int = 90
    show_player: bool = True
    show_debug_overlay: bool = True
    map_mode: str = "default"
    track_seed: int = 42
    fitness_strategy: str = "baseline_distance"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuntimeSettings":
        defaults = cls()
        return cls(
            nickname=str(data.get("nickname", defaults.nickname)),
            fps=int(data.get("fps", defaults.fps)),
            population_size=int(data.get("population_size", defaults.population_size)),
            mutation_rate=int(data.get("mutation_rate", defaults.mutation_rate)),
            show_player=bool(data.get("show_player", defaults.show_player)),
            show_debug_overlay=bool(
                data.get("show_debug_overlay", defaults.show_debug_overlay)
            ),
            map_mode=str(data.get("map_mode", defaults.map_mode)),
            track_seed=int(data.get("track_seed", defaults.track_seed)),
            fitness_strategy=str(
                data.get("fitness_strategy", defaults.fitness_strategy)
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class WeightPayload:
    model_version: str
    layer_sizes: list[int]
    weights: list[list[float]]
    biases: list[list[float]]
    fitness_score: float
    generation: int
    track_id: str
    track_seed: int
    nickname: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WeightPayload":
        return cls(
            model_version=str(data["model_version"]),
            layer_sizes=[int(value) for value in data["layer_sizes"]],
            weights=[
                [float(weight) for weight in layer_weights]
                for layer_weights in data["weights"]
            ],
            biases=[
                [float(bias) for bias in layer_biases]
                for layer_biases in data["biases"]
            ],
            fitness_score=float(data["fitness_score"]),
            generation=int(data["generation"]),
            track_id=str(data["track_id"]),
            track_seed=int(data["track_seed"]),
            nickname=str(data["nickname"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ReplayRequest:
    submission_id: str
    track_seed: int
    render_mode: str = "big-screen"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReplayRequest":
        return cls(
            submission_id=str(data["submission_id"]),
            track_seed=int(data["track_seed"]),
            render_mode=str(data.get("render_mode", "big-screen")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
