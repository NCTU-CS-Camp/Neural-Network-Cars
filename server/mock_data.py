from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from server.models import CompetitionId
from server.storage import CompetitionStorage
from shared.contracts import (
    EXPECTED_BIAS_LENGTHS,
    EXPECTED_WEIGHT_LENGTHS,
    ClientResult,
    SubmissionPayload,
)


def build_mock_payload(index: int, seed: int) -> SubmissionPayload:
    rng = np.random.default_rng(seed + index)
    return SubmissionPayload(
        group_id=str((index % 5) + 1),
        username=f"player{index + 1}",
        weights=[rng.normal(0.0, 0.05, length).astype(float).tolist() for length in EXPECTED_WEIGHT_LENGTHS],
        biases=[rng.normal(0.0, 0.05, length).astype(float).tolist() for length in EXPECTED_BIAS_LENGTHS],
    )


def build_mock_result(index: int) -> ClientResult:
    if index % 4 == 0:
        return ClientResult(True, 300 + index * 5, 4_000.0, 300 + index * 5)
    return ClientResult(False, None, 500.0 + index * 150.0, 120 + index * 10)


def create_mock_submissions(
    *,
    storage: CompetitionStorage,
    count: int = 10,
    seed: int = 42,
    competition_id: CompetitionId | str = CompetitionId.EASY,
    state: str = "queued",
    reset: bool = False,
) -> list[dict]:
    identifier = CompetitionId(competition_id)
    if reset:
        storage.reset()

    submissions = []
    for index in range(count):
        submission = storage.create_submission(
            identifier,
            build_mock_payload(index, seed),
            build_mock_result(index),
        )
        submissions.append(submission)
    if state == "completed" and identifier is not CompetitionId.FINAL:
        storage.seal_phase_one_batches(now=storage.now(), force=True)
        submissions = [
            storage.get_submission(identifier, submission["submission_id"]) or submission
            for submission in submissions
        ]
    return submissions


def main() -> None:
    parser = argparse.ArgumentParser(description="Create trusted client-result demo submissions.")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--competition", choices=[item.value for item in CompetitionId], default="easy")
    parser.add_argument("--state", choices=["queued", "completed"], default="queued")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    storage = CompetitionStorage(args.db)
    submissions = create_mock_submissions(
        storage=storage,
        count=args.count,
        seed=args.seed,
        competition_id=args.competition,
        state=args.state,
        reset=args.reset,
    )
    print(f"Created {len(submissions)} {args.state} {args.competition} submissions")
    for row in storage.leaderboard(args.competition):
        print(f"#{row['rank']} {row['username']} group={row['group_id']} {row['client_result']}")


if __name__ == "__main__":
    main()
