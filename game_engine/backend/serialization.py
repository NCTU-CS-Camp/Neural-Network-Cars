from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from shared.contracts import (
    EXPECTED_LAYER_SIZES,
    SubmissionPayload,
    WeightPayload,
)


def _flatten_layers(layers: list[np.ndarray]) -> list[list[float]]:
    return [layer.astype(float).flatten().tolist() for layer in layers]


def export_weight_payload(
    car: Any,
    generation: int,
    track_id: str,
    track_seed: int,
    nickname: str,
    fitness_score: float | None = None,
) -> WeightPayload:
    score = float(
        getattr(car, "fitness_score", 0.0)
        if fitness_score is None
        else fitness_score
    )
    return WeightPayload(
        model_version="v1",
        layer_sizes=[int(size) for size in car.sizes],
        weights=_flatten_layers(car.weights),
        biases=_flatten_layers(car.biases),
        fitness_score=score,
        generation=generation,
        track_id=track_id,
        track_seed=track_seed,
        nickname=nickname,
    )


def export_submission_payload(
    *,
    car: Any,
    group_id: str,
    username: str,
) -> SubmissionPayload:
    return SubmissionPayload(
        group_id=group_id,
        username=username,
        weights=_flatten_layers(car.weights),
        biases=_flatten_layers(car.biases),
    )


def apply_weight_payload(
    car: Any,
    payload: WeightPayload | SubmissionPayload,
) -> None:
    layer_sizes = (
        payload.layer_sizes
        if isinstance(payload, WeightPayload)
        else EXPECTED_LAYER_SIZES
    )
    expected_layers = len(layer_sizes) - 1
    if expected_layers != len(car.weights):
        raise ValueError("Layer count does not match car model.")

    for index in range(expected_layers):
        rows = layer_sizes[index + 1]
        cols = layer_sizes[index]
        car.weights[index] = np.array(payload.weights[index]).reshape(rows, cols)
        car.biases[index] = np.array(payload.biases[index]).reshape(rows, 1)


def save_weight_payload(
    payload: WeightPayload | SubmissionPayload,
    path: Path,
) -> None:
    path.write_text(json.dumps(payload.to_dict(), indent=2), encoding="utf-8")


def load_weight_payload(path: Path) -> WeightPayload | SubmissionPayload:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "group_id" in data:
        return SubmissionPayload.from_dict(data)
    return WeightPayload.from_dict(data)
