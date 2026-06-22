from __future__ import annotations

import argparse
from pathlib import Path
from typing import Protocol

import numpy as np

from server.evaluator import OfficialEvaluator
from server.models import CompetitionPhase, EvaluationResult, OfficialMap
from server.storage import CompetitionStorage
from shared.contracts import (
    EXPECTED_BIAS_LENGTHS,
    EXPECTED_WEIGHT_LENGTHS,
    SubmissionPayload,
)


class Evaluator(Protocol):
    def evaluate(
        self,
        payload: SubmissionPayload,
        official_map: OfficialMap | str,
    ) -> EvaluationResult:
        ...


def build_mock_payload(index: int, seed: int) -> SubmissionPayload:
    rng = np.random.default_rng(seed + index)
    weights = [
        rng.normal(0.0, 0.05, length).astype(float).tolist()
        for length in EXPECTED_WEIGHT_LENGTHS
    ]
    biases = [
        rng.normal(0.0, 0.05, length).astype(float).tolist()
        for length in EXPECTED_BIAS_LENGTHS
    ]
    steering_biases = [-0.8, -0.35, 0.0, 0.35, 0.8]
    steering = steering_biases[index % len(steering_biases)]
    biases[-1] = [2.5, -3.0, steering, -steering]
    return SubmissionPayload(
        group_id=str((index % 5) + 1),
        username=f"player{index + 1}",
        weights=weights,
        biases=biases,
    )


def create_mock_submissions(
    *,
    storage: CompetitionStorage,
    evaluator: Evaluator,
    count: int = 10,
    seed: int = 42,
    phase: CompetitionPhase | str | None = None,
    state: str = "pending",
    reset: bool = False,
) -> list[dict]:
    phase_value = CompetitionPhase(phase or storage.active_phase())
    if reset:
        storage.reset_phase(phase_value)

    submissions = []
    official_map = storage.active_map(phase_value)
    for index in range(count):
        payload = build_mock_payload(index, seed)
        submission = storage.create_submission(payload, phase=phase_value)
        if state == "evaluated":
            result = evaluator.evaluate(payload, official_map)
            storage.mark_evaluated(submission["submission_id"], result)
            stored_submission = storage.get_submission(submission["submission_id"])
            if stored_submission is not None:
                submission = stored_submission
        submissions.append(submission)
    return submissions


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create mock competition submissions for backend testing."
    )
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--phase", choices=["personal", "group"], default=None)
    parser.add_argument("--state", choices=["pending", "evaluated"], default="pending")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    storage = CompetitionStorage(args.db)
    submissions = create_mock_submissions(
        storage=storage,
        evaluator=OfficialEvaluator(),
        count=args.count,
        seed=args.seed,
        phase=args.phase,
        state=args.state,
        reset=args.reset,
    )
    print(f"Created {len(submissions)} {args.state} mock submissions")
    for row in storage.leaderboard(limit=30):
        print(
            f"#{row['rank']} {row['username']} group={row['group_id']} "
            f"laps={row['score_laps']:.3f}"
        )


if __name__ == "__main__":
    main()
