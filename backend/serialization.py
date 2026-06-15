from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from shared.contracts import WeightPayload


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
    score = float(car.score if fitness_score is None else fitness_score)
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


def apply_weight_payload(car: Any, payload: WeightPayload) -> None:
    expected_layers = len(payload.layer_sizes) - 1
    if expected_layers != len(car.weights):
        raise ValueError("Layer count does not match car model.")

    for index in range(expected_layers):
        rows = payload.layer_sizes[index + 1]
        cols = payload.layer_sizes[index]
        car.weights[index] = np.array(payload.weights[index]).reshape(rows, cols)
        car.biases[index] = np.array(payload.biases[index]).reshape(rows, 1)


def save_weight_payload(payload: WeightPayload, path: Path) -> None:
    path.write_text(json.dumps(payload.to_dict(), indent=2), encoding="utf-8")


def load_weight_payload(path: Path) -> WeightPayload:
    data = json.loads(path.read_text(encoding="utf-8"))
    return WeightPayload.from_dict(data)

