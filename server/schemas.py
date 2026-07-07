from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from server.competition_config import (
    FRAME_LIMIT,
    MAX_SUBMISSION_BYTES,
    validate_phase_one_batch_minutes,
)
from server.models import CompetitionStage
from shared.contracts import ClientResult, SubmissionPayload


class IdentityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_id: str = Field(min_length=1, max_length=40)
    username: str = Field(min_length=1, max_length=40)

    def clean_identity(self) -> tuple[str, str]:
        group_id = self.group_id.strip()
        username = self.username.strip()
        if not group_id or not username:
            raise ValueError("group_id and username must not be blank")
        return group_id, username


class LoginIn(IdentityIn):
    password: str = Field(min_length=1, max_length=80)

    def clean_login(self) -> tuple[str, str, str]:
        group_id, username = self.clean_identity()
        password = self.password.strip()
        if not password:
            raise ValueError("password must not be blank")
        return group_id, username, password


class NicknameUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nickname: str = Field(min_length=1, max_length=20)


class ClientResultIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    completed: bool
    lap_ticks: int | None
    max_progress: float = Field(ge=0, le=100)
    ticks_to_max_progress: int

    def to_client_result(self) -> ClientResult:
        data = self.model_dump() if hasattr(self, "model_dump") else self.dict()
        return ClientResult.from_dict(data)


class SubmissionIn(IdentityIn):
    weights: list[list[float]]
    biases: list[list[float]]
    client_result: ClientResultIn
    skin_id: int | None = None
    max_speed: float | None = None
    maxSpeed: float | None = None

    def to_submission(self) -> tuple[SubmissionPayload, ClientResult]:
        data: dict[str, Any] = self.model_dump() if hasattr(self, "model_dump") else self.dict()
        if len(json.dumps(data, separators=(",", ":")).encode("utf-8")) > MAX_SUBMISSION_BYTES:
            raise ValueError("submission payload exceeds maximum size")
        payload = SubmissionPayload.from_dict(data)
        client_result = self.client_result.to_client_result()
        if client_result.ticks_to_max_progress > FRAME_LIMIT:
            raise ValueError("client_result.ticks_to_max_progress exceeds frame limit")
        if client_result.lap_ticks is not None and client_result.lap_ticks > FRAME_LIMIT:
            raise ValueError("client_result.lap_ticks exceeds frame limit")
        return payload, client_result


class AdminUserRequest(LoginIn):
    disabled: bool = False
    nickname: str | None = Field(default=None, min_length=1, max_length=20)


class AdminUserImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    users: list[AdminUserRequest] | None = None
    text: str | None = None


class AdminStageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: CompetitionStage


class AdminConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase_one_batch_minutes: int | None = None
    snapshot_interval_minutes: int | None = None

    def clean_phase_one_batch_minutes(self) -> int:
        values = [
            value
            for value in (self.phase_one_batch_minutes, self.snapshot_interval_minutes)
            if value is not None
        ]
        if not values:
            raise ValueError("snapshot_interval_minutes is required")
        if len(set(values)) > 1:
            raise ValueError("snapshot interval fields must match")
        return validate_phase_one_batch_minutes(values[0])
