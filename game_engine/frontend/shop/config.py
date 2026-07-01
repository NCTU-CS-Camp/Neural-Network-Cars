"""All tunable shop numbers live here. Edit these values; do not edit logic.

The author replaces the placeholder numbers below (probabilities, costs,
rewards, thresholds). Comments mark what must hold (e.g. probabilities sum to 1).
"""

from __future__ import annotations

# --- Tiers, rarest first ---
TIERS: tuple[str, ...] = ("SSR", "SR", "S", "A", "B", "C")

# Draw probability per tier. MUST sum to 1.0. (placeholder — author tunes)
TIER_PROBABILITIES: dict[str, float] = {
    "SSR": 0.02,
    "SR": 0.05,
    "S": 0.10,
    "A": 0.18,
    "B": 0.30,
    "C": 0.35,
}

# Tiers that satisfy the 10-pull floor guarantee ("A or above").
GUARANTEE_TIERS: tuple[str, ...] = ("SSR", "SR", "S", "A")

# --- Gacha costs (coins) ---
SINGLE_PULL_COST: int = 10
TEN_PULL_COST: int = 90  # slight discount vs 10x single (author tunes)
TEN_PULL_COUNT: int = 10

# --- Earning rewards (coins) ---
GENERATION_REWARD: int = 1

# training reach-finish reward keyed by map_difficulty (1 easy, 2 hard, 3 random)
TRAINING_FINISH_REWARD: dict[int, int] = {1: 3, 2: 5, 3: 7}

# First-time validation milestones: (milestone_key, max_seconds, reward).
# A run awards every unclaimed milestone whose completion time is <= its
# threshold, so a fast run can unlock several at once. hard values are
# placeholders for the author to fill in.
EASY_VALIDATION_MILESTONES: list[tuple[str, float, int]] = [
    ("easy_val_15s", 15.0, 20),
    ("easy_val_12s", 12.0, 30),
    ("easy_val_10s", 10.0, 40),
]
HARD_VALIDATION_MILESTONES: list[tuple[str, float, int]] = [
    # ("hard_val_20s", 20.0, 30),  # author fills in real thresholds/amounts
]

# Random validation maps vary per seed, so reward on completion, not on time.
# Set the reward > 0 to enable it.
RANDOM_VALIDATION_COMPLETION_REWARD: int = 0
RANDOM_VALIDATION_MILESTONE_KEY: str = "random_val_complete"

# The free starter skin everyone owns and equips by default.
DEFAULT_SKIN_ID: int = 0
