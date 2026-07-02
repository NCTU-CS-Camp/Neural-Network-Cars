"""Single and 10-pull gacha. Resolves identity internally, deducts coins and
records owned skins in one save per pull. Duplicates are allowed with no
compensation. The 10-pull guarantees at least one A-or-above skin.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from game_engine.frontend.shop import catalog, store
from game_engine.frontend.shop.config import (
    GUARANTEE_TIERS,
    SINGLE_PULL_COST,
    TEN_PULL_COST,
    TEN_PULL_COUNT,
    TIER_PROBABILITIES,
    TIERS,
)


@dataclass(frozen=True)
class PullResult:
    skin_id: int
    tier: str
    name: str
    duplicate: bool


def _roll_tier(rng: random.Random) -> str:
    roll = rng.random()
    cumulative = 0.0
    for tier in TIERS:
        cumulative += TIER_PROBABILITIES.get(tier, 0.0)
        if roll <= cumulative:
            return tier
    return TIERS[-1]


def _draw_one(
    rng: random.Random, owned: set[int], force_tier: str | None = None
) -> PullResult:
    tier = force_tier or _roll_tier(rng)
    pool = catalog.skins_by_tier(tier) or catalog.all_skins()
    skin = rng.choice(pool)
    duplicate = skin.id in owned
    owned.add(skin.id)
    return PullResult(skin.id, skin.tier, skin.name, duplicate)


def single_pull(rng: random.Random | None = None) -> PullResult | None:
    """Return the drawn skin, or None if no profile / insufficient coins."""
    rng = rng or random.Random()
    identity = store.active_identity()
    if identity is None:
        return None
    entry = store.load_entry(identity)
    if int(entry["coins"]) < SINGLE_PULL_COST:
        return None
    entry["coins"] = int(entry["coins"]) - SINGLE_PULL_COST
    owned = set(entry["owned_skins"])
    result = _draw_one(rng, owned)
    entry["owned_skins"] = sorted(owned)
    store.save_entry(identity, entry)
    return result


def ten_pull(rng: random.Random | None = None) -> list[PullResult] | None:
    """Return 10 drawn skins (>=1 A-or-above), or None if unaffordable/no profile."""
    rng = rng or random.Random()
    identity = store.active_identity()
    if identity is None:
        return None
    entry = store.load_entry(identity)
    if int(entry["coins"]) < TEN_PULL_COST:
        return None
    entry["coins"] = int(entry["coins"]) - TEN_PULL_COST
    owned = set(entry["owned_skins"])
    results = [_draw_one(rng, owned) for _ in range(TEN_PULL_COUNT)]
    if not any(result.tier in GUARANTEE_TIERS for result in results):
        results[-1] = _draw_one(rng, owned, force_tier=GUARANTEE_TIERS[-1])
    entry["owned_skins"] = sorted(owned)
    store.save_entry(identity, entry)
    return results
