from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from shared.contracts import (
    EXPECTED_BIAS_SHAPES,
    EXPECTED_LAYER_SIZES,
    EXPECTED_WEIGHT_SHAPES,
    WeightPayload,
)


class SubmissionIn(BaseModel):
    model_version: str = "v1"
    layer_sizes: list[int]
    weights: list[list[float]]
    biases: list[list[float]]
    fitness_score: float = 0.0
    generation: int = 0
    track_id: str = "client"
    track_seed: int = 0
    nickname: str = Field(min_length=1, max_length=40)

    def to_weight_payload(self) -> WeightPayload:
        data = self.model_dump() if hasattr(self, "model_dump") else self.dict()
        validate_weight_payload(data)
        return WeightPayload.from_dict(data)


class SubmissionCreateResponse(BaseModel):
    submission_id: str
    status: str


class AdminReplayRequest(BaseModel):
    submission_id: str


def validate_weight_payload(data: dict[str, Any]) -> None:
    layer_sizes = [int(value) for value in data.get("layer_sizes", [])]
    if layer_sizes != EXPECTED_LAYER_SIZES:
        raise ValueError(f"layer_sizes must be {EXPECTED_LAYER_SIZES}")

    weights = data.get("weights", [])
    biases = data.get("biases", [])
    if len(weights) != len(EXPECTED_WEIGHT_SHAPES):
        raise ValueError("weights must contain exactly two layers")
    if len(biases) != len(EXPECTED_BIAS_SHAPES):
        raise ValueError("biases must contain exactly two layers")

    for index, shape in enumerate(EXPECTED_WEIGHT_SHAPES):
        expected_length = shape[0] * shape[1]
        if len(weights[index]) != expected_length:
            raise ValueError(
                f"weights[{index}] must contain {expected_length} values"
            )

    for index, shape in enumerate(EXPECTED_BIAS_SHAPES):
        expected_length = shape[0] * shape[1]
        if len(biases[index]) != expected_length:
            raise ValueError(
                f"biases[{index}] must contain {expected_length} values"
            )
