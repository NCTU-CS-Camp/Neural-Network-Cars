from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any


# Fixed network shape expected by the trusted competition server (Competition
# Server team's shared/contracts.py). Submission payloads must match exactly.
EXPECTED_LAYER_SIZES = [6, 6, 4]
EXPECTED_WEIGHT_SHAPES = [(6, 6), (4, 6)]
EXPECTED_BIAS_SHAPES = [(6, 1), (4, 1)]
EXPECTED_WEIGHT_LENGTHS = [rows * cols for rows, cols in EXPECTED_WEIGHT_SHAPES]
EXPECTED_BIAS_LENGTHS = [rows * cols for rows, cols in EXPECTED_BIAS_SHAPES]
DEFAULT_SERVER_URL = "http://127.0.0.1:8000"


def _float_layers(raw_layers: Any, expected_lengths: list[int], field_name: str) -> list[list[float]]:
    if not isinstance(raw_layers, list):
        raise ValueError(f"{field_name} must be a list of layers")
    if len(raw_layers) != len(expected_lengths):
        raise ValueError(f"{field_name} must contain exactly {len(expected_lengths)} layers")

    layers: list[list[float]] = []
    for index, expected_length in enumerate(expected_lengths):
        raw_layer = raw_layers[index]
        if not isinstance(raw_layer, list):
            raise ValueError(f"{field_name}[{index}] must be a list")
        if len(raw_layer) != expected_length:
            raise ValueError(f"{field_name}[{index}] must contain {expected_length} values")
        values = [float(value) for value in raw_layer]
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"{field_name}[{index}] must contain only finite values")
        layers.append(values)
    return layers


@dataclass(slots=True)
class RuntimeSettings:
    nickname: str = "player1"
    server_url: str = DEFAULT_SERVER_URL
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
            server_url=str(data.get("server_url", defaults.server_url)),
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
    server_url: str = DEFAULT_SERVER_URL

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LoginProfile":
        return cls(
            group_id=str(data["group_id"]),
            username=str(data["username"]),
            server_url=str(data.get("server_url", DEFAULT_SERVER_URL)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SubmissionPayload:
    """Weights/biases payload accepted by the trusted competition server."""

    group_id: str
    username: str
    weights: list[list[float]]
    biases: list[list[float]]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SubmissionPayload":
        group_id = str(data["group_id"]).strip()
        username = str(data["username"]).strip()
        if not group_id:
            raise ValueError("group_id must not be empty")
        if not username:
            raise ValueError("username must not be empty")
        return cls(
            group_id=group_id,
            username=username,
            weights=_float_layers(data.get("weights"), EXPECTED_WEIGHT_LENGTHS, "weights"),
            biases=_float_layers(data.get("biases"), EXPECTED_BIAS_LENGTHS, "biases"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ClientResult:
    """Client-side run metrics reported alongside a competition submission."""

    completed: bool
    lap_ticks: int | None
    max_progress: float
    ticks_to_max_progress: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def ranking_key(self) -> tuple[int, int, float, int]:
        """Lower keys rank ahead of higher keys."""
        if self.completed:
            return (0, self.lap_ticks or 0, 0.0, 0)
        return (1, 0, -self.max_progress, self.ticks_to_max_progress)


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
    weights: list[list[float]]
    biases: list[list[float]]
    fitness_config: FitnessConfig
    map_difficulty: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TrainingRecord":
        return cls(
            record_id=str(data["record_id"]),
            record_name=str(data["record_name"]),
            saved_at=str(data["saved_at"]),
            group_id=str(data["group_id"]),
            username=str(data["username"]),
            layer_sizes=[int(size) for size in data["layer_sizes"]],
            weights=[[float(w) for w in layer] for layer in data["weights"]],
            biases=[[float(b) for b in layer] for layer in data["biases"]],
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
            "weights": self.weights,
            "biases": self.biases,
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
