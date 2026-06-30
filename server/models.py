from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class CompetitionPhase(StrEnum):
    PERSONAL = "personal"
    GROUP = "group"


class CompetitionStage(StrEnum):
    PHASE_ONE = "phase_one"
    FINAL = "final"


class CompetitionId(StrEnum):
    EASY = "easy"
    HARD = "hard"
    FINAL = "final"


class SubmissionStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class CheckpointGate:
    index: int
    center: tuple[float, float]
    a: tuple[float, float]
    b: tuple[float, float]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CheckpointGate":
        return cls(
            index=int(data["index"]),
            center=(float(data["center"][0]), float(data["center"][1])),
            a=(float(data["a"][0]), float(data["a"][1])),
            b=(float(data["b"][0]), float(data["b"][1])),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "center": list(self.center),
            "a": list(self.a),
            "b": list(self.b),
        }


@dataclass(frozen=True, slots=True)
class OfficialMap:
    map_id: str
    name: str
    front_path: str
    back_path: str
    metadata_path: str
    spawn_x: float
    spawn_y: float
    spawn_angle: float
    checkpoints: list[CheckpointGate]
    route_cells: list[tuple[int, int]]

    @classmethod
    def from_metadata(cls, metadata: dict[str, Any]) -> "OfficialMap":
        spawn = metadata["spawn"]
        return cls(
            map_id=str(metadata["map_id"]),
            name=str(metadata["name"]),
            front_path=str(metadata["front_path"]),
            back_path=str(metadata["back_path"]),
            metadata_path=str(metadata["metadata_path"]),
            spawn_x=float(spawn["x"]),
            spawn_y=float(spawn["y"]),
            spawn_angle=float(spawn.get("angle", 180.0)),
            checkpoints=[
                CheckpointGate.from_dict(checkpoint)
                for checkpoint in metadata["checkpoints"]
            ],
            route_cells=[
                (int(cell[0]), int(cell[1]))
                for cell in metadata.get("route_cells", [])
            ],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "map_id": self.map_id,
            "name": self.name,
            "front_path": self.front_path,
            "back_path": self.back_path,
            "metadata_path": self.metadata_path,
            "spawn": {
                "x": self.spawn_x,
                "y": self.spawn_y,
                "angle": self.spawn_angle,
            },
            "route_cells": [
                [cell[0], cell[1]] for cell in self.route_cells
            ],
            "checkpoints": [
                checkpoint.to_dict() for checkpoint in self.checkpoints
            ],
        }


@dataclass(slots=True)
class EvaluationResult:
    score_laps: float
    frames_simulated: int
    collided: bool
    checkpoints_completed: int
    completed_laps: int
    map_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def new_submission_id() -> str:
    return f"sub_{uuid4().hex[:8]}"


def new_batch_id() -> str:
    return f"batch_{uuid4().hex[:10]}"
