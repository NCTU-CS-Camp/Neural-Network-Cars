from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from shared.contracts import EXPECTED_LAYER_SIZES, SubmissionPayload, WeightPayload


def _flatten_layers(layers: list[np.ndarray]) -> list[list[float]]:
    return [layer.astype(float).flatten().tolist() for layer in layers]


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


def export_weight_payload(
    car: Any,
    generation: int | None = None,
    track_id: str | None = None,
    track_seed: int | None = None,
    nickname: str | None = None,
    fitness_score: float | None = None,
    *,
    group_id: str = "1",
    username: str | None = None,
) -> WeightPayload:
    del generation, track_id, track_seed, fitness_score
    return export_submission_payload(
        car=car,
        group_id=group_id,
        username=username or nickname or "player1",
    )


def apply_weight_payload(car: Any, payload: SubmissionPayload) -> None:
    expected_layers = len(EXPECTED_LAYER_SIZES) - 1
    if expected_layers != len(car.weights):
        raise ValueError("Layer count does not match car model.")

    for index in range(expected_layers):
        rows = EXPECTED_LAYER_SIZES[index + 1]
        cols = EXPECTED_LAYER_SIZES[index]
        car.weights[index] = np.array(payload.weights[index]).reshape(rows, cols)
        car.biases[index] = np.array(payload.biases[index]).reshape(rows, 1)


def save_weight_payload(payload: SubmissionPayload, path: Path) -> None:
    path.write_text(json.dumps(payload.to_dict(), indent=2), encoding="utf-8")


def load_weight_payload(path: Path) -> SubmissionPayload:
    data = json.loads(path.read_text(encoding="utf-8"))
    return SubmissionPayload.from_dict(data)
