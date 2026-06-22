from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from server.models import CompetitionPhase
from shared.contracts import (
    EXPECTED_BIAS_LENGTHS,
    EXPECTED_WEIGHT_LENGTHS,
    SubmissionPayload,
)


class SubmissionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_id: str = Field(min_length=1, max_length=40)
    username: str = Field(min_length=1, max_length=40)
    weights: list[list[float]]
    biases: list[list[float]]

    def to_submission_payload(self) -> SubmissionPayload:
        data = self.model_dump() if hasattr(self, "model_dump") else self.dict()
        validate_submission_payload(data)
        return SubmissionPayload.from_dict(data)


class SubmissionCreateResponse(BaseModel):
    submission_id: str
    status: str
    phase: str


class AdminPhaseRequest(BaseModel):
    phase: CompetitionPhase


class AdminMapRequest(BaseModel):
    phase: CompetitionPhase
    map_id: str


def validate_submission_payload(data: dict) -> None:
    payload = SubmissionPayload.from_dict(data)
    for index, expected_length in enumerate(EXPECTED_WEIGHT_LENGTHS):
        if len(payload.weights[index]) != expected_length:
            raise ValueError(
                f"weights[{index}] must contain {expected_length} values"
            )
    for index, expected_length in enumerate(EXPECTED_BIAS_LENGTHS):
        if len(payload.biases[index]) != expected_length:
            raise ValueError(
                f"biases[{index}] must contain {expected_length} values"
            )
