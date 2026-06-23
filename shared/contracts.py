from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from collections.abc import Mapping
from typing import Any, ClassVar


# Fixed network shape expected by the trusted competition server (Competition
# Server team's shared/contracts.py). Submission payloads must match exactly.
EXPECTED_LAYER_SIZES = [6, 6, 4]
EXPECTED_WEIGHT_SHAPES = [(6, 6), (4, 6)]
EXPECTED_BIAS_SHAPES = [(6, 1), (4, 1)]
EXPECTED_WEIGHT_LENGTHS = [rows * cols for rows, cols in EXPECTED_WEIGHT_SHAPES]
EXPECTED_BIAS_LENGTHS = [rows * cols for rows, cols in EXPECTED_BIAS_SHAPES]
DEFAULT_SERVER_URL = "http://127.0.0.1:8000"
DEFAULT_EVOLUTION_SEED = 3057


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
    group_id: str = "1"
    username: str = "player1"
    nickname: str = "player1"
    server_url: str = DEFAULT_SERVER_URL
    fps: int = 30
    population_size: int = 50
    mutation_rate: int = 90
    show_player: bool = True
    show_debug_overlay: bool = True
    map_mode: str = "default"
    track_seed: int = 42
    evolution_seed: int = DEFAULT_EVOLUTION_SEED
    max_speed: int = 10

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuntimeSettings":
        defaults = cls()
        username = str(
            data.get("username", data.get("nickname", defaults.username))
        )
        return cls(
            group_id=str(data.get("group_id", defaults.group_id)),
            username=username,
            nickname=str(data.get("nickname", username)),
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
            evolution_seed=int(
                data.get("evolution_seed", defaults.evolution_seed)
            ),
            max_speed=max(5, min(30, int(data.get("max_speed", defaults.max_speed)))),
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


FitnessWeight = int | float

_LEGACY_FITNESS_WEIGHT_NAMES = {
    "speed_score": "speed",
    "progress_score": "progress",
    "completion_bonus": "centered",
    "smooth_control": "alignment",
    "checkpoint_reward": "safety",
    "stagnation_penalty": "stall",
    "spin_penalty": "spin",
    "reverse_penalty": "wrong_way",
    "time_penalty": "time",
    "collision_penalty": "crash",
}


@dataclass(slots=True, init=False)
class FitnessConfig:
    speed: FitnessWeight
    progress: FitnessWeight
    centered: FitnessWeight
    alignment: FitnessWeight
    safety: FitnessWeight
    stall: FitnessWeight
    spin: FitnessWeight
    wrong_way: FitnessWeight
    time: FitnessWeight
    crash: FitnessWeight

    WEIGHT_NAMES: ClassVar[tuple[str, ...]] = (
        "speed",
        "progress",
        "centered",
        "alignment",
        "safety",
        "stall",
        "spin",
        "wrong_way",
        "time",
        "crash",
    )

    def __init__(
        self,
        *,
        speed: FitnessWeight = 0,
        progress: FitnessWeight = 0,
        centered: FitnessWeight = 0,
        alignment: FitnessWeight = 0,
        safety: FitnessWeight = 0,
        stall: FitnessWeight = 0,
        spin: FitnessWeight = 0,
        wrong_way: FitnessWeight = 0,
        time: FitnessWeight = 0,
        crash: FitnessWeight = 0,
        weights: Mapping[str, FitnessWeight] | None = None,
    ) -> None:
        values: dict[str, FitnessWeight] = {
            "speed": speed,
            "progress": progress,
            "centered": centered,
            "alignment": alignment,
            "safety": safety,
            "stall": stall,
            "spin": spin,
            "wrong_way": wrong_way,
            "time": time,
            "crash": crash,
        }
        if weights is not None:
            unknown_names = set(weights) - set(self.WEIGHT_NAMES)
            if unknown_names:
                raise ValueError(
                    "Unsupported fitness keys: "
                    + ", ".join(sorted(unknown_names))
                )
            values.update(weights)

        for name, value in values.items():
            setattr(self, name, _coerce_fitness_weight(name, value))

    @property
    def weights(self) -> dict[str, FitnessWeight]:
        """Return a serializable snapshot of all ten weights."""
        return {name: getattr(self, name) for name in self.WEIGHT_NAMES}

    @classmethod
    def weight_names(cls) -> tuple[str, ...]:
        return cls.WEIGHT_NAMES

    def copy(self) -> "FitnessConfig":
        return type(self)(weights=self.weights)

    def get_weight(self, name: str) -> FitnessWeight:
        if name not in self.WEIGHT_NAMES:
            raise ValueError(f"Unsupported fitness key: {name}")
        return getattr(self, name)

    def set_weight(self, name: str, value: FitnessWeight) -> None:
        if name not in self.WEIGHT_NAMES:
            raise ValueError(f"Unsupported fitness key: {name}")
        setattr(self, name, _coerce_fitness_weight(name, value))

    def update_weights(self, weights: Mapping[str, FitnessWeight]) -> None:
        unknown_names = set(weights) - set(self.WEIGHT_NAMES)
        if unknown_names:
            raise ValueError(
                "Unsupported fitness keys: " + ", ".join(sorted(unknown_names))
            )
        for name, value in weights.items():
            self.set_weight(name, value)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FitnessConfig":
        raw_weights = data.get("weights", data)
        return cls(
            weights={
                _LEGACY_FITNESS_WEIGHT_NAMES.get(str(key), str(key)):
                    _coerce_fitness_weight(str(key), value)
                for key, value in raw_weights.items()
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {"weights": self.weights}


def _coerce_fitness_weight(name: str, value: Any) -> FitnessWeight:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"Fitness weight {name!r} must be numeric")
    numeric = float(value)
    return int(numeric) if numeric.is_integer() else numeric


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
    max_speed: int = 10
    best_fitness_score: float | None = None
    mlp_init_seed: int = DEFAULT_EVOLUTION_SEED
    mlp_init_rng_state: dict[str, Any] | None = None
    mutation_rng_state: tuple[Any, ...] | list[Any] | None = None

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
            max_speed=max(5, min(30, int(data.get("max_speed", 10)))),
            best_fitness_score=(
                float(data["best_fitness_score"])
                if data.get("best_fitness_score") is not None
                else None
            ),
            mlp_init_seed=int(
                data.get("mlp_init_seed", DEFAULT_EVOLUTION_SEED)
            ),
            mlp_init_rng_state=data.get("mlp_init_rng_state"),
            mutation_rng_state=data.get("mutation_rng_state"),
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
            "max_speed": self.max_speed,
            "best_fitness_score": self.best_fitness_score,
            "mlp_init_seed": self.mlp_init_seed,
            "mlp_init_rng_state": self.mlp_init_rng_state,
            "mutation_rng_state": self.mutation_rng_state,
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
