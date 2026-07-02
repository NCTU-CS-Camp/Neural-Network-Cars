"""Coin earning/spending. Resolves the active identity internally, so gameplay
hooks call these as one-liners without threading identity. All functions are
no-ops when no profile is logged in.
"""

from __future__ import annotations

from typing import Any

from game_engine.backend.settings import FPS
from game_engine.frontend.shop import store
from game_engine.frontend.shop.config import (
    EASY_VALIDATION_MILESTONES,
    HARD_VALIDATION_MILESTONES,
    RANDOM_VALIDATION_MILESTONES,
    TRAINING_FINISH_REWARD,
)


def balance() -> int:
    identity = store.active_identity()
    if identity is None:
        return 0
    return int(store.load_entry(identity)["coins"])


def award(amount: int) -> None:
    """Add coins (repeatable). No-op for non-positive amounts or no profile."""
    if amount <= 0:
        return
    identity = store.active_identity()
    if identity is None:
        return
    entry = store.load_entry(identity)
    entry["coins"] = int(entry["coins"]) + amount
    store.save_entry(identity, entry)


def award_milestone(key: str, amount: int) -> bool:
    """Award a first-time-only milestone. Returns True if newly awarded."""
    if amount <= 0:
        return False
    identity = store.active_identity()
    if identity is None:
        return False
    entry = store.load_entry(identity)
    if key in entry["claimed_milestones"]:
        return False
    entry["claimed_milestones"].append(key)
    entry["coins"] = int(entry["coins"]) + amount
    store.save_entry(identity, entry)
    return True


def spend(amount: int) -> bool:
    """Deduct coins if affordable. Returns True on success."""
    if amount <= 0:
        return False
    identity = store.active_identity()
    if identity is None:
        return False
    entry = store.load_entry(identity)
    if int(entry["coins"]) < amount:
        return False
    entry["coins"] = int(entry["coins"]) - amount
    store.save_entry(identity, entry)
    return True


def award_training_finish(map_difficulty: int) -> None:
    """Reward for a training car reaching the finish (1 easy / 2 hard / 3 random)."""
    award(TRAINING_FINISH_REWARD.get(map_difficulty, 0))


def award_validation(
    map_id: str, client_result: Any, map_key: str | None = None
) -> list[tuple[str, int]]:
    """Award first-time validation milestones for a completed run.

    ``map_key`` scopes the milestone to a specific map instance. Fixed easy/hard
    maps pass None so each threshold is a once-ever reward. Random maps pass a
    per-map fingerprint so a threshold is claimable once per distinct map: a new
    random map earns again, but re-clearing one you already beat does not.

    Returns the list of (key, reward) newly awarded (for UI/debug).
    """
    awarded: list[tuple[str, int]] = []

    if map_id == "easy":
        milestones = EASY_VALIDATION_MILESTONES
    elif map_id == "hard":
        milestones = HARD_VALIDATION_MILESTONES
    elif map_id == "random":
        milestones = RANDOM_VALIDATION_MILESTONES
    else:
        return awarded

    if client_result is None or not client_result.completed:
        return awarded
    if client_result.lap_ticks is None:
        return awarded

    seconds = client_result.lap_ticks / FPS
    for key, threshold, reward in milestones:
        claim_key = f"{key}:{map_key}" if map_key else key
        if seconds <= threshold and award_milestone(claim_key, reward):
            awarded.append((claim_key, reward))
    return awarded
