from __future__ import annotations

from server.mock_data import build_mock_payload, create_mock_submissions, main
from server.storage import CompetitionStorage


def seed_demo_players(
    *,
    storage: CompetitionStorage,
    count: int = 5,
    seed: int = 42,
    reset: bool = True,
) -> list[dict]:
    return create_mock_submissions(
        storage=storage,
        count=count,
        seed=seed,
        state="completed",
        reset=reset,
    )


def build_demo_payload(player_index: int, seed: int):
    return build_mock_payload(player_index - 1, seed)


if __name__ == "__main__":
    main()
