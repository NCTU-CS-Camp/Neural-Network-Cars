# Shop / Skin Gacha Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a client-side, local shop where players earn coins from gameplay milestones and spend them on a cosmetic car-skin gacha.

**Architecture:** All new code lives in an isolated subpackage `game_engine/frontend/shop/` (config, catalog, store, wallet, gacha, renderer, screen). State persists to a git-ignored `shop_state.json` keyed by `group_id::username`. Identity, coins, owned skins, equipped skin, and claimed milestones are resolved internally from the saved login profile, so integration into existing files (`app.py`, `screens.py`) is limited to small additive insertions. Skins are cosmetic only — they reskin the car base sprites at render time and never touch weights, submissions, or the leaderboard.

**Tech Stack:** Python 3.12, Pygame, `uv` for running. No automated tests (per author request) — each task ends with a lightweight run/verify command and a commit.

**Conventions:**
- Run everything with `uv run ...` from the repo root `Neural-Network-Cars/`.
- Keep `uv run ruff check game_engine` green after every task.
- The author will later tune all numeric values in `config.py` and drop art into `Images/Skins/`.

---

## Task 1: Config module + skins asset dir + gitignore

**Files:**
- Create: `game_engine/frontend/shop/__init__.py`
- Create: `game_engine/frontend/shop/config.py`
- Create: `Images/Skins/.gitkeep`
- Modify: `.gitignore`

- [ ] **Step 1: Create the package marker**

Create `game_engine/frontend/shop/__init__.py`:

```python
"""Client-side local shop: coins, skin gacha, and cosmetic skin rendering."""
```

- [ ] **Step 2: Create the config module**

Create `game_engine/frontend/shop/config.py`:

```python
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
```

- [ ] **Step 3: Create the skins asset directory**

Create `Images/Skins/.gitkeep` with an empty content (a placeholder so the dir is tracked; image-mode skins load their PNGs from here later).

```
```

- [ ] **Step 4: Ignore the runtime state file**

In `.gitignore`, find the block:

```
# Local runtime configuration and user data
.env
profile.json
records.json
settings.json
```

Add `shop_state.json` under it:

```
# Local runtime configuration and user data
.env
profile.json
records.json
settings.json
shop_state.json
```

- [ ] **Step 5: Verify config imports and probabilities sum to 1**

Run:
```bash
uv run python -c "from game_engine.frontend.shop import config as c; import math; print('sum', sum(c.TIER_PROBABILITIES.values())); assert math.isclose(sum(c.TIER_PROBABILITIES.values()), 1.0); print('ok')"
```
Expected: prints `sum 1.0` then `ok`.

- [ ] **Step 6: Commit**

```bash
git add game_engine/frontend/shop/__init__.py game_engine/frontend/shop/config.py Images/Skins/.gitkeep .gitignore
git commit -m "feat(shop): add config module, skins asset dir, gitignore state file"
```

---

## Task 2: Skin catalog

**Files:**
- Create: `game_engine/frontend/shop/catalog.py`

- [ ] **Step 1: Create the catalog**

Create `game_engine/frontend/shop/catalog.py`:

```python
"""Static skin catalog. Each skin declares its render mode so both a tinted
base sprite and a loaded PNG image work. The author edits/extends SKINS and
drops matching art into Images/Skins/ for image-mode skins.

render dict shapes:
  {"type": "tint",  "base": "white"|"green", "color": (r, g, b)}
  {"type": "image", "path": "Images/Skins/<name>"}   # loads <path>_small.png / <path>_big.png
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Skin:
    id: int
    name: str
    tier: str
    render: dict[str, Any]


# Placeholder catalog: enough to exercise every tier before real art arrives.
SKINS: list[Skin] = [
    Skin(0, "Default", "C", {"type": "tint", "base": "white", "color": (255, 255, 255)}),
    Skin(1, "Coal", "C", {"type": "tint", "base": "white", "color": (90, 90, 90)}),
    Skin(2, "Moss", "B", {"type": "tint", "base": "green", "color": (120, 180, 90)}),
    Skin(3, "Sky", "B", {"type": "tint", "base": "white", "color": (120, 200, 255)}),
    Skin(4, "Amber", "A", {"type": "tint", "base": "white", "color": (255, 190, 70)}),
    Skin(5, "Rose", "S", {"type": "tint", "base": "white", "color": (255, 120, 160)}),
    Skin(6, "Violet", "SR", {"type": "tint", "base": "white", "color": (170, 110, 255)}),
    Skin(7, "Aurora", "SSR", {"type": "image", "path": "Images/Skins/aurora"}),
]

_BY_ID: dict[int, Skin] = {skin.id: skin for skin in SKINS}


def all_skins() -> list[Skin]:
    return list(SKINS)


def get_skin(skin_id: int) -> Skin:
    """Return the skin, falling back to the default (id 0) if unknown."""
    return _BY_ID.get(skin_id, _BY_ID[0])


def skins_by_tier(tier: str) -> list[Skin]:
    return [skin for skin in SKINS if skin.tier == tier]
```

- [ ] **Step 2: Verify catalog covers every tier**

Run:
```bash
uv run python -c "from game_engine.frontend.shop import catalog, config; missing=[t for t in config.TIERS if not catalog.skins_by_tier(t)]; print('missing tiers:', missing); assert not missing; print('default:', catalog.get_skin(999).name); print('ok')"
```
Expected: `missing tiers: []`, then `default: Default`, then `ok`.

- [ ] **Step 3: Commit**

```bash
git add game_engine/frontend/shop/catalog.py
git commit -m "feat(shop): add skin catalog with tier coverage"
```

---

## Task 3: Persistence store

**Files:**
- Create: `game_engine/frontend/shop/store.py`

- [ ] **Step 1: Create the store**

Create `game_engine/frontend/shop/store.py`:

```python
"""shop_state.json persistence, keyed by identity (group_id::username).

Each identity entry: coins, owned_skins, equipped_skin, claimed_milestones.
Identity is resolved from the saved login profile so callers never thread it.
Load/save helpers accept explicit identity + path for headless use.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from game_engine.backend.settings import PROJECT_ROOT
from game_engine.frontend.profile_store import load_login_profile
from game_engine.frontend.shop.config import DEFAULT_SKIN_ID

SHOP_STATE_PATH = PROJECT_ROOT / "shop_state.json"


def _default_entry() -> dict[str, Any]:
    return {
        "coins": 0,
        "owned_skins": [DEFAULT_SKIN_ID],
        "equipped_skin": DEFAULT_SKIN_ID,
        "claimed_milestones": [],
    }


def active_identity() -> str | None:
    """Return 'group_id::username' from the saved login profile, or None."""
    profile = load_login_profile()
    if profile is None:
        return None
    return f"{profile.group_id}::{profile.username}"


def _load_all(path: Path = SHOP_STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    content = path.read_text(encoding="utf-8")
    if not content.strip():
        return {}
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _save_all(data: dict[str, Any], path: Path = SHOP_STATE_PATH) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load_entry(identity: str, path: Path = SHOP_STATE_PATH) -> dict[str, Any]:
    """Return the identity's entry, filled with defaults for missing keys."""
    entry = _load_all(path).get(identity)
    merged = _default_entry()
    if isinstance(entry, dict):
        merged.update(entry)
    return merged


def save_entry(
    identity: str, entry: dict[str, Any], path: Path = SHOP_STATE_PATH
) -> None:
    data = _load_all(path)
    data[identity] = entry
    _save_all(data, path)
```

- [ ] **Step 2: Verify round-trip persistence (headless, temp file)**

Run:
```bash
uv run python -c "
from pathlib import Path
import tempfile
from game_engine.frontend.shop import store
p = Path(tempfile.gettempdir()) / 'shop_test.json'
p.unlink(missing_ok=True)
e = store.load_entry('1::alice', p)
print('default', e)
e['coins'] = 25
e['owned_skins'] = [0, 3]
store.save_entry('1::alice', e, p)
print('reloaded', store.load_entry('1::alice', p))
print('other identity isolated', store.load_entry('2::bob', p))
p.unlink(missing_ok=True)
print('ok')
"
```
Expected: default entry with `coins 0`, reloaded shows `coins 25`/`owned_skins [0, 3]`, `2::bob` shows a fresh default entry, then `ok`.

- [ ] **Step 3: Commit**

```bash
git add game_engine/frontend/shop/store.py
git commit -m "feat(shop): add per-identity shop_state.json persistence"
```

---

## Task 4: Wallet (earning logic)

**Files:**
- Create: `game_engine/frontend/shop/wallet.py`

- [ ] **Step 1: Create the wallet**

Create `game_engine/frontend/shop/wallet.py`:

```python
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
    RANDOM_VALIDATION_COMPLETION_REWARD,
    RANDOM_VALIDATION_MILESTONE_KEY,
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


def award_validation(map_id: str, client_result: Any) -> list[tuple[str, int]]:
    """Award first-time validation milestones for a completed run.

    Returns the list of (key, reward) newly awarded (for UI/debug).
    """
    awarded: list[tuple[str, int]] = []

    if map_id == "random":
        if (
            RANDOM_VALIDATION_COMPLETION_REWARD > 0
            and client_result is not None
            and client_result.completed
            and award_milestone(
                RANDOM_VALIDATION_MILESTONE_KEY, RANDOM_VALIDATION_COMPLETION_REWARD
            )
        ):
            awarded.append(
                (RANDOM_VALIDATION_MILESTONE_KEY, RANDOM_VALIDATION_COMPLETION_REWARD)
            )
        return awarded

    if map_id == "easy":
        milestones = EASY_VALIDATION_MILESTONES
    elif map_id == "hard":
        milestones = HARD_VALIDATION_MILESTONES
    else:
        return awarded

    if client_result is None or not client_result.completed:
        return awarded
    if client_result.lap_ticks is None:
        return awarded

    seconds = client_result.lap_ticks / FPS
    for key, threshold, reward in milestones:
        if seconds <= threshold and award_milestone(key, reward):
            awarded.append((key, reward))
    return awarded
```

- [ ] **Step 2: Verify milestone logic (headless, monkeypatched identity/path)**

Run:
```bash
uv run python -c "
from pathlib import Path
import tempfile
from dataclasses import dataclass
from game_engine.frontend.shop import wallet, store
from game_engine.backend.settings import FPS

p = Path(tempfile.gettempdir()) / 'shop_wallet_test.json'
p.unlink(missing_ok=True)
store.SHOP_STATE_PATH = p
store.active_identity = lambda: '1::alice'

@dataclass
class CR:
    completed: bool
    lap_ticks: int | None

# 9s easy run unlocks all three easy milestones once (20+30+40=90)
print('first', wallet.award_validation('easy', CR(True, int(9*FPS))))
print('second (dupes blocked)', wallet.award_validation('easy', CR(True, int(9*FPS))))
print('balance', wallet.balance())
wallet.award(5); wallet.award(5)
print('after generation awards', wallet.balance())
print('spend 50 ->', wallet.spend(50), 'balance', wallet.balance())
print('spend 9999 ->', wallet.spend(9999), 'balance', wallet.balance())
p.unlink(missing_ok=True)
print('ok')
"
```
Expected: first awards three milestones, second awards `[]`, balance `90`, after awards `100`, spend 50 True → balance `50`, spend 9999 False → balance `50`, then `ok`.

- [ ] **Step 3: Commit**

```bash
git add game_engine/frontend/shop/wallet.py
git commit -m "feat(shop): add wallet earning/spending and validation milestones"
```

---

## Task 5: Skin renderer + apply_equipped_skin

**Files:**
- Create: `game_engine/frontend/shop/renderer.py`

- [ ] **Step 1: Create the renderer**

Create `game_engine/frontend/shop/renderer.py`:

```python
"""Resolve a skin_id into {small, big} pygame surfaces, and apply the equipped
skin onto a GameAssets bundle. Tint mode recolors a base sprite; image mode
loads PNGs from the skin's path. Missing/broken assets fall back to the default
white sprite with a warning so the game keeps running before real art exists.

Requires the pygame display to be initialized (surfaces use convert_alpha).
"""

from __future__ import annotations

from typing import Any

import pygame

from game_engine.backend.settings import PROJECT_ROOT, SPRITES_DIR
from game_engine.frontend.shop import catalog
from game_engine.frontend.shop.config import DEFAULT_SKIN_ID

_cache: dict[int, dict[str, pygame.Surface]] = {}


def _load_base(base: str) -> tuple[pygame.Surface, pygame.Surface]:
    color = base if base in ("white", "green") else "white"
    small = pygame.image.load(str(SPRITES_DIR / f"{color}_small.png")).convert_alpha()
    big = pygame.image.load(str(SPRITES_DIR / f"{color}_big.png")).convert_alpha()
    return small, big


def _tinted(surface: pygame.Surface, color: tuple[int, int, int]) -> pygame.Surface:
    tinted = surface.copy()
    tinted.fill((*color, 255), special_flags=pygame.BLEND_RGBA_MULT)
    return tinted


def _render(skin_render: dict[str, Any]) -> dict[str, pygame.Surface]:
    if skin_render.get("type") == "image":
        path = skin_render["path"]
        small = pygame.image.load(
            str(PROJECT_ROOT / f"{path}_small.png")
        ).convert_alpha()
        big = pygame.image.load(str(PROJECT_ROOT / f"{path}_big.png")).convert_alpha()
        return {"small": small, "big": big}
    base_small, base_big = _load_base(skin_render.get("base", "white"))
    color = skin_render.get("color", (255, 255, 255))
    return {"small": _tinted(base_small, color), "big": _tinted(base_big, color)}


def surfaces_for(skin_id: int) -> dict[str, pygame.Surface]:
    if skin_id in _cache:
        return _cache[skin_id]
    skin = catalog.get_skin(skin_id)
    try:
        result = _render(skin.render)
    except (pygame.error, FileNotFoundError, KeyError, OSError) as exc:
        print(f"[shop] skin {skin_id} render failed ({exc}); using default sprite")
        base_small, base_big = _load_base("white")
        result = {"small": base_small, "big": base_big}
    _cache[skin_id] = result
    return result


def apply_equipped_skin(assets: Any) -> None:
    """Reskin the car base sprites on a GameAssets bundle to the equipped skin.

    No-op when no profile is logged in or the default skin is equipped, so
    stock behavior is unchanged unless the player opted into a skin.
    """
    from game_engine.frontend.shop import store

    identity = store.active_identity()
    if identity is None:
        return
    equipped = int(store.load_entry(identity)["equipped_skin"])
    if equipped == DEFAULT_SKIN_ID:
        return
    surfaces = surfaces_for(equipped)
    assets.white_small_car = surfaces["small"]
    assets.green_small_car = surfaces["small"]
    assets.white_big_car = surfaces["big"]
    assets.green_big_car = surfaces["big"]
```

- [ ] **Step 2: Verify tint rendering headless (offscreen pygame)**

Run:
```bash
uv run python -c "
import os
os.environ['SDL_VIDEODRIVER'] = 'dummy'
import pygame
pygame.display.init(); pygame.display.set_mode((64, 64))
from game_engine.frontend.shop import renderer
s = renderer.surfaces_for(1)  # Coal, tint
print('tint sizes', s['small'].get_size(), s['big'].get_size())
img = renderer.surfaces_for(7)  # Aurora image (missing art) -> fallback
print('image-fallback sizes', img['small'].get_size())
print('ok')
"
```
Expected: prints two size tuples for the tint skin, a size tuple for the fallback (with a `[shop] skin 7 render failed ...` warning line above it), then `ok`.

- [ ] **Step 3: Commit**

```bash
git add game_engine/frontend/shop/renderer.py
git commit -m "feat(shop): add skin renderer with tint/image/fallback and apply_equipped_skin"
```

---

## Task 6: Gacha

**Files:**
- Create: `game_engine/frontend/shop/gacha.py`

- [ ] **Step 1: Create the gacha module**

Create `game_engine/frontend/shop/gacha.py`:

```python
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
```

- [ ] **Step 2: Verify tier distribution and 10-pull guarantee (headless)**

Run:
```bash
uv run python -c "
import random
from collections import Counter
from game_engine.frontend.shop import gacha, config
rng = random.Random(42)
tiers = Counter(gacha._roll_tier(rng) for _ in range(20000))
print('distribution', {t: round(tiers[t]/20000, 3) for t in config.TIERS})
# guarantee: every 10-pull draws >=1 A-or-above
owned=set()
for _ in range(300):
    res=[gacha._draw_one(rng, owned) for _ in range(10)]
    if not any(r.tier in config.GUARANTEE_TIERS for r in res):
        res[-1]=gacha._draw_one(rng, owned, force_tier=config.GUARANTEE_TIERS[-1])
    assert any(r.tier in config.GUARANTEE_TIERS for r in res)
print('guarantee held for 300 ten-pulls')
print('ok')
"
```
Expected: a distribution roughly matching `TIER_PROBABILITIES`, `guarantee held for 300 ten-pulls`, then `ok`.

- [ ] **Step 3: Commit**

```bash
git add game_engine/frontend/shop/gacha.py
git commit -m "feat(shop): add single/10-pull gacha with tier roll and floor guarantee"
```

---

## Task 7: Shop screen (UI)

**Files:**
- Create: `game_engine/frontend/shop/screen.py`

- [ ] **Step 1: Create the shop screen**

Create `game_engine/frontend/shop/screen.py`:

```python
"""Shop scene: coin balance, gacha (single / 10-pull) with a result strip, and
an inventory grid of owned skins that can be equipped. Blocking loop mirroring
the other screens in game_engine/frontend/screens.py.
"""

from __future__ import annotations

import random

import pygame

from game_engine.backend.settings import BLACK, CJK_FONT_PATH, FONT_PATH, WHITE
from game_engine.frontend.shop import catalog, gacha, store
from game_engine.frontend.shop.config import SINGLE_PULL_COST, TEN_PULL_COST
from game_engine.frontend.shop.renderer import surfaces_for
from game_engine.frontend.widgets import Button

_TIER_COLORS: dict[str, tuple[int, int, int]] = {
    "SSR": (255, 190, 70),
    "SR": (200, 130, 255),
    "S": (255, 120, 160),
    "A": (120, 200, 255),
    "B": (150, 210, 150),
    "C": (180, 180, 180),
}


def _font(size: int = 22) -> pygame.font.Font:
    path = CJK_FONT_PATH or str(FONT_PATH)
    return pygame.font.Font(path, size)


def run_shop_screen(screen: pygame.Surface) -> None:
    clock = pygame.time.Clock()
    font = _font(22)
    title_font = _font(34)
    small_font = _font(16)
    width, height = screen.get_size()
    rng = random.Random()

    identity = store.active_identity()

    back_button = Button("返回", pygame.Rect(60, 40, 140, 48))
    single_button = Button(
        f"單抽 ({SINGLE_PULL_COST})", pygame.Rect(60, 200, 240, 60)
    )
    ten_button = Button(f"十連 ({TEN_PULL_COST})", pygame.Rect(320, 200, 240, 60))

    last_results: list[gacha.PullResult] = []
    message = ""

    # Inventory cells are computed each frame from owned skins.
    def owned_skins() -> list[int]:
        if identity is None:
            return []
        return list(store.load_entry(identity)["owned_skins"])

    def equipped_skin() -> int:
        if identity is None:
            return 0
        return int(store.load_entry(identity)["equipped_skin"])

    def balance() -> int:
        if identity is None:
            return 0
        return int(store.load_entry(identity)["coins"])

    def inventory_cell_rect(index: int) -> pygame.Rect:
        columns = 6
        cell = 96
        gap = 16
        grid_x = 60
        grid_y = 380
        row, col = divmod(index, columns)
        return pygame.Rect(
            grid_x + col * (cell + gap),
            grid_y + row * (cell + gap + 20),
            cell,
            cell,
        )

    def equip(skin_id: int) -> None:
        if identity is None:
            return
        entry = store.load_entry(identity)
        entry["equipped_skin"] = skin_id
        store.save_entry(identity, entry)

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                pos = event.pos
                if back_button.contains(pos):
                    return
                if single_button.contains(pos):
                    result = gacha.single_pull(rng)
                    if result is None:
                        message = "金錢不足或尚未登入"
                    else:
                        last_results = [result]
                        message = ""
                elif ten_button.contains(pos):
                    results = gacha.ten_pull(rng)
                    if results is None:
                        message = "金錢不足或尚未登入"
                    else:
                        last_results = results
                        message = ""
                else:
                    for index, skin_id in enumerate(owned_skins()):
                        if inventory_cell_rect(index).collidepoint(pos):
                            equip(skin_id)
                            break

        mouse_pos = pygame.mouse.get_pos()
        for button in (back_button, single_button, ten_button):
            button.update_hover(mouse_pos)

        screen.fill(BLACK)
        screen.blit(title_font.render("商店", True, WHITE), (60, 110))
        screen.blit(
            font.render(f"金錢: {balance()}", True, (255, 220, 120)), (width - 260, 120)
        )
        back_button.draw(screen, font)
        single_button.draw(screen, font)
        ten_button.draw(screen, font)

        # Gacha result strip
        screen.blit(font.render("抽獎結果", True, WHITE), (60, 290))
        for index, result in enumerate(last_results):
            cell = pygame.Rect(60 + index * 92, 320, 84, 40)
            color = _TIER_COLORS.get(result.tier, WHITE)
            pygame.draw.rect(screen, color, cell, 2, border_radius=4)
            label = f"{result.tier}{'*' if result.duplicate else ''}"
            screen.blit(small_font.render(label, True, color), (cell.x + 8, cell.y + 10))
        if message:
            screen.blit(font.render(message, True, (255, 120, 120)), (600, 215))

        # Inventory
        screen.blit(font.render("我的車庫 (點擊裝備)", True, WHITE), (60, 348))
        current = equipped_skin()
        for index, skin_id in enumerate(owned_skins()):
            rect = inventory_cell_rect(index)
            skin = catalog.get_skin(skin_id)
            sprite = surfaces_for(skin_id)["small"]
            sprite = pygame.transform.scale(sprite, (rect.width - 16, rect.height - 16))
            border = (
                (255, 220, 120) if skin_id == current else _TIER_COLORS.get(skin.tier, WHITE)
            )
            pygame.draw.rect(screen, border, rect, 3, border_radius=6)
            screen.blit(sprite, (rect.x + 8, rect.y + 8))
            screen.blit(small_font.render(skin.name, True, WHITE), (rect.x, rect.bottom + 2))

        pygame.display.update()
        clock.tick(30)
```

- [ ] **Step 2: Verify the module imports cleanly**

Run:
```bash
uv run python -c "from game_engine.frontend.shop.screen import run_shop_screen; print('ok')"
```
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add game_engine/frontend/shop/screen.py
git commit -m "feat(shop): add shop screen UI with gacha and equip inventory"
```

---

## Task 8: Wire the Shop into the home menu

**Files:**
- Modify: `game_engine/frontend/screens.py` (`MenuChoice` at line 99; `run_main_menu_screen` at lines 221-267)
- Modify: `game_engine/frontend/app.py` (main menu dispatch at lines 107-134)

- [ ] **Step 1: Add "shop" to MenuChoice**

In `game_engine/frontend/screens.py`, change line 99 from:

```python
MenuChoice = Literal["training", "validation", "clear_user"]
```

to:

```python
MenuChoice = Literal["training", "validation", "shop", "clear_user"]
```

- [ ] **Step 2: Add the Shop button to the main menu**

In `game_engine/frontend/screens.py`, in `run_main_menu_screen`, after the `clear_user_button` definition (ends at line 239), add a Shop button:

```python
    shop_button = Button(
        "商店",
        pygame.Rect(width // 2 - 160, height // 2 + 210, 320, 56),
        fill_color=(30, 70, 60),
        hover_color=(40, 100, 85),
        border_color=(70, 170, 140),
    )
```

Then in the event loop, after the `clear_user_button` hit-test (lines 249-250), add:

```python
                if shop_button.contains(event.pos):
                    return "shop"
```

Then after `clear_user_button.update_hover(mouse_pos)` (line 255) add:

```python
        shop_button.update_hover(mouse_pos)
```

Then after `clear_user_button.draw(screen, font)` (line 264) add:

```python
        shop_button.draw(screen, font)
```

- [ ] **Step 3: Dispatch "shop" in the app main loop**

In `game_engine/frontend/app.py`, add the import near the other frontend imports (after line 58, `from game_engine.frontend.profile_store import save_login_profile`):

```python
from game_engine.frontend.shop.screen import run_shop_screen
```

Then change the dispatch block at lines 117-134 from:

```python
            if choice == "training":
                result = run_training_config_screen(screen, settings.max_speed)
                if result is not None:
                    fitness_strategy, map_difficulty, parent_record, max_speed = result
                    settings.max_speed = max_speed
                    save_runtime_settings(settings)
                    if map_difficulty == 3:
                        generate_random_map(screen)
                    run_training_loop(
                        screen,
                        settings,
                        profile,
                        fitness_strategy,
                        map_difficulty,
                        parent_record,
                    )
            else:
                run_validation_list_screen(screen, profile.server_url)
```

to:

```python
            if choice == "training":
                result = run_training_config_screen(screen, settings.max_speed)
                if result is not None:
                    fitness_strategy, map_difficulty, parent_record, max_speed = result
                    settings.max_speed = max_speed
                    save_runtime_settings(settings)
                    if map_difficulty == 3:
                        generate_random_map(screen)
                    run_training_loop(
                        screen,
                        settings,
                        profile,
                        fitness_strategy,
                        map_difficulty,
                        parent_record,
                    )
            elif choice == "shop":
                run_shop_screen(screen)
            else:
                run_validation_list_screen(screen, profile.server_url)
```

- [ ] **Step 4: Verify the app starts and the menu renders (manual)**

Run:
```bash
uv run python main.py
```
Expected: after logging in, the main menu shows a **商店** button under the clear-user button. Clicking it opens the shop (balance 0, gacha + empty-but-Default inventory). `返回`/Esc returns to the menu. Close the window to exit.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check game_engine
git add game_engine/frontend/screens.py game_engine/frontend/app.py
git commit -m "feat(shop): add Shop entry to home menu and app dispatch"
```

---

## Task 9: Earning hooks (generations, training finish, validation milestones)

**Files:**
- Modify: `game_engine/frontend/app.py` (`run_training_loop`: `redraw_game_window` at lines 428-439; loop setup before line 551; main loop after `redraw_game_window()` at line 614)
- Modify: `game_engine/frontend/screens.py` (`_run_record_validation_screen` at lines 1054-1057)

- [ ] **Step 1: Import wallet + config reward in app.py**

In `game_engine/frontend/app.py`, add near the shop import from Task 8:

```python
from game_engine.frontend.shop import wallet
from game_engine.frontend.shop.config import GENERATION_REWARD
```

- [ ] **Step 2: Award training-finish inside the step loop**

In `game_engine/frontend/app.py`, at the top of the nested `redraw_game_window` function (right after its `def redraw_game_window():` line 428, before `map_canvas.blit(bg, (0, 0))`), add:

```python
        nonlocal finish_awarded_this_gen
```

Then change the population step loop (lines 432-436) from:

```python
        for nn_car in nn_cars:
            if not nn_car.collided:
                step_result = simulator.step(nn_car, fitness_strategy.score_frame)
                if step_result.telemetry.collided:
                    session.mark_collision(nn_car)
```

to:

```python
        for nn_car in nn_cars:
            if not nn_car.collided:
                step_result = simulator.step(nn_car, fitness_strategy.score_frame)
                if step_result.telemetry.collided:
                    session.mark_collision(nn_car)
                if step_result.telemetry.finished_now and not finish_awarded_this_gen:
                    wallet.award_training_finish(map_difficulty)
                    finish_awarded_this_gen = True
```

- [ ] **Step 3: Initialize the reward trackers before the main loop**

In `game_engine/frontend/app.py`, just before `while True:` at line 551 (after `car.refresh_track_state(track)` line 549), add:

```python
    last_awarded_generation = session.generation
    finish_awarded_this_gen = False
```

- [ ] **Step 4: Award per-generation coins and reset the finish flag**

In `game_engine/frontend/app.py`, in the main `while True:` loop, after `redraw_game_window()` (line 614) and before `if session.should_end_generation(...)` (line 615), add:

```python
        if session.generation > last_awarded_generation:
            wallet.award(GENERATION_REWARD * (session.generation - last_awarded_generation))
            last_awarded_generation = session.generation
            finish_awarded_this_gen = False
```

- [ ] **Step 5: Award validation milestones**

In `game_engine/frontend/screens.py`, add the wallet import near the other frontend imports (after the `from game_engine.frontend.profile_store import ...` / widgets import area, e.g. after line 59):

```python
from game_engine.frontend.shop import wallet as shop_wallet
```

Then in `_run_record_validation_screen`, change lines 1056-1057 from:

```python
    client_result, survival_ticks = outcome
    _validation_result_screen(screen, map_id, client_result, survival_ticks)
```

to:

```python
    client_result, survival_ticks = outcome
    shop_wallet.award_validation(map_id, client_result)
    _validation_result_screen(screen, map_id, client_result, survival_ticks)
```

- [ ] **Step 6: Verify earning end-to-end (manual)**

Run:
```bash
uv run python main.py
```
Expected:
- Start an **easy** training run, let a few generations pass (or click 下一代): the shop balance rises by `GENERATION_REWARD` per generation.
- When a car reaches the finish line during a generation, balance jumps by the training-finish reward (3 easy / 5 hard / 7 random), once per generation.
- Run **Validation → easy** and complete it under 15s: the first time, the shop balance rises by the milestone reward(s); repeating the same milestone pays nothing.

Open the Shop from the menu to confirm the balance.

- [ ] **Step 7: Lint and commit**

```bash
uv run ruff check game_engine
git add game_engine/frontend/app.py game_engine/frontend/screens.py
git commit -m "feat(shop): award coins for generations, training finishes, validation milestones"
```

---

## Task 10: Apply the equipped skin in training and validation

**Files:**
- Modify: `game_engine/frontend/app.py` (`run_training_loop` after `assets = load_game_assets()` at line 153)
- Modify: `game_engine/frontend/screens.py` (`_run_validation_tournament_screen` after `assets = load_game_assets()` at line 1368)

- [ ] **Step 1: Import apply_equipped_skin in app.py**

In `game_engine/frontend/app.py`, add near the other shop imports:

```python
from game_engine.frontend.shop.renderer import apply_equipped_skin
```

- [ ] **Step 2: Reskin the training assets**

In `game_engine/frontend/app.py`, change line 153 from:

```python
    assets = load_game_assets()
```

to:

```python
    assets = load_game_assets()
    apply_equipped_skin(assets)
```

- [ ] **Step 3: Import and apply in the validation tournament**

In `game_engine/frontend/screens.py`, add near the wallet import from Task 9:

```python
from game_engine.frontend.shop.renderer import apply_equipped_skin
```

Then in `_run_validation_tournament_screen`, change line 1368 from:

```python
    assets = load_game_assets()
```

to:

```python
    assets = load_game_assets()
    apply_equipped_skin(assets)
```

- [ ] **Step 4: Verify skins apply (manual)**

Run:
```bash
uv run python main.py
```
Expected:
- Open the Shop, pull until you own a non-default tint skin (e.g. Coal/Sky), and click it to equip (its cell gets a gold border).
- Start a training run: the cars render in the equipped skin's color instead of white.
- Run a validation: the candidate cars also render in the equipped skin.
- Equip the Default skin again → cars render in stock white/green (unchanged behavior).

- [ ] **Step 5: Lint, type-check, and commit**

```bash
uv run ruff check game_engine
uv run mypy game_engine
git add game_engine/frontend/app.py game_engine/frontend/screens.py
git commit -m "feat(shop): apply equipped skin to training and validation cars"
```

---

## Final verification

- [ ] **Full flow (manual):**
  1. `uv run python main.py`, log in.
  2. Train (easy): balance climbs with generations; finishing a lap adds the finish reward once per generation.
  3. Validation (easy) under a threshold: first-time milestone pays out; repeat pays nothing.
  4. Shop: single and 10-pull deduct coins; 10-pull always yields at least one A-or-above; duplicates are marked `*`.
  5. Equip a skin; confirm training + validation cars reskin; re-equip Default restores stock sprites.
  6. Restart the app; confirm `shop_state.json` kept the balance, owned skins, equipped skin, and claimed milestones.
- [ ] **Lint/type clean:** `uv run ruff check .` and `uv run mypy game_engine` both pass.
- [ ] **Isolation check:** `git diff --name-only main...feature/shop-skins` shows only the shop subpackage, `app.py`, `screens.py`, `.gitignore`, `Images/Skins/.gitkeep`, and the docs — no server/GA/shared changes.

## Notes for the author (values to fill in `config.py`)

- `TIER_PROBABILITIES` — final per-tier odds (must sum to 1.0).
- `SINGLE_PULL_COST`, `TEN_PULL_COST` — final gacha prices.
- `HARD_VALIDATION_MILESTONES` — hard-validation time thresholds + rewards.
- `RANDOM_VALIDATION_COMPLETION_REWARD` — set > 0 to reward random-validation completion.
- `catalog.SKINS` — real skin roster per tier; add `image`-mode entries and drop `<name>_small.png` / `<name>_big.png` into `Images/Skins/`.
