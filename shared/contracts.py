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
class LoginProfile:
    group_id: str
    username: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LoginProfile":
        return cls(
            group_id=str(data["group_id"]),
            username=str(data["username"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class FitnessConfig:
    weights: dict[str, int]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FitnessConfig":
        return cls(weights={str(key): int(value) for key, value in data["weights"].items()})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TrainingRecord:
    record_id: str
    record_name: str
    saved_at: str
    group_id: str
    username: str
    layer_sizes: list[int]
    parent_a_weights: list[list[float]]
    parent_a_biases: list[list[float]]
    parent_b_weights: list[list[float]]
    parent_b_biases: list[list[float]]
    fitness_config: FitnessConfig
    map_difficulty: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TrainingRecord":
        # backward compat: old records stored single weights/biases
        legacy_weights = [[float(w) for w in layer] for layer in data["weights"]] if "weights" in data else []
        legacy_biases = [[float(b) for b in layer] for layer in data["biases"]] if "biases" in data else []
        return cls(
            record_id=str(data["record_id"]),
            record_name=str(data["record_name"]),
            saved_at=str(data["saved_at"]),
            group_id=str(data["group_id"]),
            username=str(data["username"]),
            layer_sizes=[int(size) for size in data["layer_sizes"]],
            parent_a_weights=[[float(w) for w in layer] for layer in data["parent_a_weights"]] if "parent_a_weights" in data else legacy_weights,
            parent_a_biases=[[float(b) for b in layer] for layer in data["parent_a_biases"]] if "parent_a_biases" in data else legacy_biases,
            parent_b_weights=[[float(w) for w in layer] for layer in data["parent_b_weights"]] if "parent_b_weights" in data else legacy_weights,
            parent_b_biases=[[float(b) for b in layer] for layer in data["parent_b_biases"]] if "parent_b_biases" in data else legacy_biases,
            fitness_config=FitnessConfig.from_dict(data["fitness_config"]),
            map_difficulty=int(data["map_difficulty"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "record_name": self.record_name,
            "saved_at": self.saved_at,
            "group_id": self.group_id,
            "username": self.username,
            "layer_sizes": self.layer_sizes,
            "parent_a_weights": self.parent_a_weights,
            "parent_a_biases": self.parent_a_biases,
            "parent_b_weights": self.parent_b_weights,
            "parent_b_biases": self.parent_b_biases,
            "fitness_config": self.fitness_config.to_dict(),
            "map_difficulty": self.map_difficulty,
        }


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
