from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any


EXPECTED_LAYER_SIZES = [6, 6, 4]
EXPECTED_WEIGHT_SHAPES = [(6, 6), (4, 6)]
EXPECTED_BIAS_SHAPES = [(6, 1), (4, 1)]
EXPECTED_WEIGHT_LENGTHS = [rows * cols for rows, cols in EXPECTED_WEIGHT_SHAPES]
EXPECTED_BIAS_LENGTHS = [rows * cols for rows, cols in EXPECTED_BIAS_SHAPES]


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
            raise ValueError(
                f"{field_name}[{index}] must contain {expected_length} values"
            )
        values = [float(value) for value in raw_layer]
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"{field_name}[{index}] must contain only finite values")
        layers.append(values)
    return layers


@dataclass(slots=True)
class RuntimeSettings:
    group_id: str = "1"
    username: str = "player1"
    # Deprecated UI compatibility field. New submissions use username.
    nickname: str = "player1"
    fps: int = 30
    population_size: int = 50
    mutation_rate: int = 90
    show_player: bool = True
    show_debug_overlay: bool = True
    map_mode: str = "default"
    track_seed: int = 42
    fitness_strategy: str = "baseline_distance"
    server_url: str = "http://127.0.0.1:8000"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuntimeSettings":
        defaults = cls()
        username = str(data.get("username", data.get("nickname", defaults.username)))
        return cls(
            group_id=str(data.get("group_id", defaults.group_id)),
            username=username,
            nickname=username,
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
            server_url=str(data.get("server_url", defaults.server_url)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SubmissionPayload:
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
    """Client-side run metrics used by the trusted competition service."""

    completed: bool
    lap_ticks: int | None
    max_progress: float
    ticks_to_max_progress: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ClientResult":
        if not isinstance(data, dict):
            raise ValueError("client_result must be an object")

        completed = data.get("completed")
        if not isinstance(completed, bool):
            raise ValueError("client_result.completed must be a boolean")

        lap_ticks = data.get("lap_ticks")
        if completed:
            if isinstance(lap_ticks, bool) or not isinstance(lap_ticks, int) or lap_ticks <= 0:
                raise ValueError(
                    "client_result.lap_ticks must be a positive integer for completed runs"
                )
        elif lap_ticks is not None:
            raise ValueError("client_result.lap_ticks must be null for incomplete runs")

        max_progress_raw = data.get("max_progress")
        if max_progress_raw is None or isinstance(max_progress_raw, bool):
            raise ValueError("client_result.max_progress must be a finite number")
        try:
            max_progress = float(max_progress_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("client_result.max_progress must be a finite number") from exc
        if not math.isfinite(max_progress) or max_progress < 0:
            raise ValueError("client_result.max_progress must be finite and non-negative")

        ticks_raw = data.get("ticks_to_max_progress")
        if isinstance(ticks_raw, bool) or not isinstance(ticks_raw, int) or ticks_raw < 0:
            raise ValueError(
                "client_result.ticks_to_max_progress must be a non-negative integer"
            )

        return cls(
            completed=completed,
            lap_ticks=lap_ticks,
            max_progress=max_progress,
            ticks_to_max_progress=ticks_raw,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def ranking_key(self) -> tuple[int, int, float, int]:
        """Lower keys rank ahead of higher keys."""
        if self.completed:
            return (0, self.lap_ticks or 0, 0.0, 0)
        return (1, 0, -self.max_progress, self.ticks_to_max_progress)


# Backwards-compatible internal alias while modules migrate to the new API name.
WeightPayload = SubmissionPayload


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
