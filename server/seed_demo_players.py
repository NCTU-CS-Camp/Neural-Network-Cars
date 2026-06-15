from __future__ import annotations

import argparse
from pathlib import Path
from typing import Protocol

import numpy as np

from server.evaluator import OfficialEvaluator
from server.models import EvaluationResult
from server.storage import CompetitionStorage
from shared.contracts import (
    EXPECTED_BIAS_SHAPES,
    EXPECTED_LAYER_SIZES,
    EXPECTED_WEIGHT_SHAPES,
    WeightPayload,
)


class Evaluator(Protocol):
    def evaluate(self, payload: WeightPayload) -> EvaluationResult:
        ...


def build_demo_payload(player_index: int, seed: int) -> WeightPayload:
    rng = np.random.default_rng(seed + player_index)
    weights = [
        rng.normal(0.0, 0.05, rows * cols).astype(float).tolist()
        for rows, cols in EXPECTED_WEIGHT_SHAPES
    ]
    biases = [
        rng.normal(0.0, 0.05, rows * cols).astype(float).tolist()
        for rows, cols in EXPECTED_BIAS_SHAPES
    ]
    steering_biases = [-0.8, -0.35, 0.0, 0.35, 0.8]
    steering = steering_biases[(player_index - 1) % len(steering_biases)]
    biases[-1] = [2.5, -3.0, steering, -steering]
    return WeightPayload(
        model_version="v1",
        layer_sizes=list(EXPECTED_LAYER_SIZES),
        weights=weights,
        biases=biases,
        fitness_score=0.0,
        generation=0,
        track_id="demo-seed",
        track_seed=seed,
        nickname=f"player{player_index}",
    )


def seed_demo_players(
    *,
    storage: CompetitionStorage,
    evaluator: Evaluator,
    count: int = 5,
    seed: int = 42,
    reset: bool = True,
) -> list[dict]:
    if reset:
        storage.reset()

    submissions = []
    for player_index in range(1, count + 1):
        payload = build_demo_payload(player_index, seed)
        submission = storage.create_submission(payload)
        result = evaluator.evaluate(payload)
        storage.mark_evaluated(submission["submission_id"], result)
        stored_submission = storage.get_submission(submission["submission_id"])
        if stored_submission is not None:
            submissions.append(stored_submission)
    return submissions


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed deterministic demo players into the competition database."
    )
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    storage = CompetitionStorage(args.db)
    submissions = seed_demo_players(
        storage=storage,
        evaluator=OfficialEvaluator(),
        count=args.count,
        seed=args.seed,
        reset=True,
    )

    print(f"Seeded {len(submissions)} demo players")
    for row in storage.leaderboard():
        score = row["official_score"] or 0.0
        print(f"{row['nickname']}: {score:.1f} ({row['best_submission_id']})")


if __name__ == "__main__":
    main()
