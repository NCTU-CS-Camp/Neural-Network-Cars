from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class SubmissionStatus(StrEnum):
    PENDING = "pending"
    EVALUATING = "evaluating"
    EVALUATED = "evaluated"
    FAILED = "failed"


@dataclass(slots=True)
class TrackScore:
    track_id: str
    track_name: str
    score: float
    frames_simulated: int
    collided: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EvaluationResult:
    official_score: float
    track_scores: list[TrackScore]
    best_track_id: str | None
    best_track_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "official_score": self.official_score,
            "track_scores": [track_score.to_dict() for track_score in self.track_scores],
            "best_track_id": self.best_track_id,
            "best_track_score": self.best_track_score,
        }


def new_submission_id() -> str:
    return f"sub_{uuid4().hex[:8]}"
