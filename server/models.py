from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from uuid import uuid4

from shared.contracts import ReplayRequest, WeightPayload


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class SubmissionRecord:
    submission_id: str
    payload: dict
    submitted_at: str

    @classmethod
    def create(cls, payload: WeightPayload) -> "SubmissionRecord":
        return cls(
            submission_id=f"sub_{uuid4().hex[:8]}",
            payload=payload.to_dict(),
            submitted_at=_utc_now(),
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class ReplayJob:
    replay_id: str
    submission_id: str
    track_seed: int
    render_mode: str
    created_at: str

    @classmethod
    def create(cls, request: ReplayRequest) -> "ReplayJob":
        return cls(
            replay_id=f"replay_{uuid4().hex[:8]}",
            submission_id=request.submission_id,
            track_seed=request.track_seed,
            render_mode=request.render_mode,
            created_at=_utc_now(),
        )

    def to_dict(self) -> dict:
        return asdict(self)

