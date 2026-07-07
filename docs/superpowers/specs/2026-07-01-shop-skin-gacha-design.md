# Shop / Skin Gacha — Design Spec

Date: 2026-07-01
Branch: `feature/shop-skins`
Status: Approved design, pending implementation plan.

## 0. Goal

Add a **client-side, local** shop to Neural Network Cars. Players earn coins by
hitting gameplay milestones, and spend coins on a gacha that awards cosmetic car
**skins**. The feature is entirely local to the game client: no server, API, or
competition-contract changes.

## 1. Principles & constraints

- **Local only.** No `server/`, `shared/`, or GA changes. `skin_id` is an integer
  key used by an in-client shop module, not a network API.
- **Cosmetic only.** Skins change only the player-visible car sprite in
  training/validation rendering. They never touch weights, `client_result`,
  submissions, cooldown, or the leaderboard.
- **Config-driven.** Every tunable number (prices, tier probabilities, reward
  amounts, time thresholds) lives in one config module and can be changed
  without editing logic.
- **Conflict-minimal.** Nearly all code lives in a new isolated subpackage
  (`game_engine/frontend/shop/`). The only shared files touched are `app.py`
  and `screens.py`, via small additive insertions. No backend/GA/server code is
  touched.

## 2. File architecture

### New files (isolated — no other team touches these)

```
game_engine/frontend/shop/
├── __init__.py
├── config.py       # all tunable numbers: prices, tier probabilities, reward amounts, thresholds
├── catalog.py      # skin definitions (id, name, tier, tint-or-image render spec)
├── store.py        # shop_state.json load/save, keyed by identity (mirrors profile_store.py)
├── wallet.py       # award() / spend() / milestone first-time tracking
├── gacha.py        # single + 10-pull draw logic
├── renderer.py     # skin_id → {small, big} surfaces (tint / load image / fallback)
└── screen.py       # run_shop_screen(...) — the shop UI

Images/Skins/        # empty until art is provided; image-mode skins load from here
```

### Modified existing files (entire conflict surface — all additive)

| File | Change |
|---|---|
| `game_engine/frontend/screens.py` | `MenuChoice` literal `+= "shop"`; add a **Shop** button in `run_main_menu_screen`; add one `award_milestone(...)` call in `_validation_result_screen` |
| `game_engine/frontend/app.py` | add dispatch branch `elif choice == "shop": run_shop_screen(...)`; in `run_training_loop`, apply equipped skin after `load_game_assets()`, and award coins on generation-advance and on finish |
| `.gitignore` | add `shop_state.json` under the existing "Local runtime configuration and user data" section |

`training_session.py` is **not** modified — generation increments are detected by
watching `session.generation` in the training loop.

## 3. Persistence

New file `shop_state.json` at project root (git-ignored, like `profile.json`),
keyed by identity so different local users keep separate wallets:

```json
{
  "1::player1": {
    "coins": 42,
    "owned_skins": [0, 3, 7],
    "equipped_skin": 3,
    "claimed_milestones": ["easy_val_15s", "easy_val_12s"]
  }
}
```

- Identity key: `f"{group_id}::{username}"`.
- `coins`: wallet balance (non-negative integer).
- `owned_skins`: list of owned `skin_id`s. Duplicates collapse to set membership
  (owning is boolean; dupes give nothing).
- `equipped_skin`: currently equipped `skin_id`. Defaults to the free starter
  skin (id `0`).
- `claimed_milestones`: keys of first-time validation milestones already paid out.
- `store.py` provides load/save and mutation helpers, mirroring `profile_store.py`.
  A missing identity entry is created lazily with defaults (coins 0, owns skin 0,
  equipped 0, no milestones).

## 4. Skin catalog & rendering

`catalog.py` defines a static list of skins across six tiers: **SSR, SR, S, A, B, C**.
Each skin declares a render mode so both art paths work:

```python
Skin(id=0,  name="Default", tier="C",   render={"type": "tint",  "base": "white", "color": (255, 255, 255)})
Skin(id=12, name="Aurora",  tier="SSR", render={"type": "image", "path": "Images/Skins/aurora"})
```

- `tint`: recolor a base sprite (`white` or `green`) at load time. Produces both
  small and big variants from the two existing base sizes.
- `image`: load PNGs provided later, expected as `<path>_small.png` and
  `<path>_big.png`.
- `renderer.py` resolves `skin_id` → cached `{small, big}` pygame surfaces. If an
  image file is missing, it falls back to the default sprite and logs a warning, so
  the mechanism runs before real art exists.
- Skin id `0` ("Default") is free, owned by everyone, and is the default equip.

## 5. Earning system

`wallet.py` exposes `award(identity, reason)` and `award_milestone(identity, key)`.
These are called from existing gameplay event points:

| Event | Hook location | Reward | Repeatable? |
|---|---|---|---|
| generation +1 | `run_training_loop` (watch `session.generation`) | 1 | yes |
| easy training reach finish | training finish detection | 3 | yes |
| hard training reach finish | training finish detection | 5 | yes |
| random training reach finish | training finish detection | 7 | yes |
| easy validation 15s | `_validation_result_screen` | 20 | first time only |
| easy validation 12s | `_validation_result_screen` | 30 | first time only |
| easy validation 10s | `_validation_result_screen` | 40 | first time only |
| hard validation (thresholds TBD) | `_validation_result_screen` | TBD | first time only |
| random validation (completion-based, TBD) | `_validation_result_screen` | TBD | first time only |

Notes:

- First-time milestones: `award_milestone` is a no-op if the key is already in
  `claimed_milestones`.
- Validation time is `lap_ticks / FPS` when `completed`, compared to thresholds.
- **Random validation** uses a freshly generated map per seed, so a fixed time
  threshold is arbitrary. Recommendation: key random-validation rewards on
  *completion* (reaching the finish at all) rather than time. Final decision is the
  author's when filling the TBD numbers.
- Coin awards from generations are trivially farmable by idling training. This is
  accepted: skins are cosmetic and local.

## 6. Gacha

`gacha.py`:

- **Single pull** and **10-pull**. Costs from `config.py` (10-pull cost is the
  author's choice — flat 10× or discounted).
- Draw: roll a tier by weighted probability (SSR…C, must sum to 1), then pick a
  skin uniformly within that tier.
- **Duplicates allowed, no compensation** — a dupe re-adds an owned id; net effect
  is coins spent, nothing gained. The result screen shows this honestly.
- **10-pull floor guarantee:** at least one skin of tier **A or above**.
- Coin deduction is checked and applied atomically; a pull is rejected if the
  balance is insufficient.
- RNG is seedable for reproducibility.

## 7. Shop UI

- A new **Shop** button on the home screen (`run_main_menu_screen`) →
  `run_shop_screen`.
- The shop screen shows:
  - Current coin balance.
  - **Gacha** panel: single-pull and 10-pull buttons, with a result display
    (skins drawn, tier, and whether each was a duplicate).
  - **Inventory** panel: grid of owned skins; click to equip; the equipped skin is
    marked.
- Equipping updates `equipped_skin`. The player car uses the equipped skin on the
  next training/validation run (applied by overlaying the equipped skin's small/big
  surfaces onto `assets.white_small_car` / `white_big_car` right after
  `load_game_assets()`).

## 8. Values the author still provides

Implementation ships placeholder defaults; the author replaces:

- Per-tier draw probabilities (SSR/SR/S/A/B/C, summing to 1).
- Single-pull and 10-pull costs.
- Number of skins per tier, and each skin's render spec (tint color or image path).
- Blank reward-table values: hard-validation thresholds + amounts, and
  random-validation trigger (completion vs time) + amounts.

## 9. Verification (manual — no automated tests per author request)

Verify by running the client (`uv run python main.py`):

- Advancing generations and finishing training maps increases coins by the
  configured amounts.
- Validation milestones pay out once and only once.
- Single and 10-pull deduct coins, respect insufficient-balance, and the 10-pull
  guarantees at least one A-or-above.
- Equipping a skin changes the car sprite on the next run.
- Tint skins recolor correctly; image skins load, and missing image files fall
  back to the default sprite without crashing.
- `shop_state.json` persists across restarts and keeps separate wallets per
  identity.
```

## 10. Out of scope

- No server/leaderboard integration.
- No trading, selling, or refund of skins.
- No real-money or external purchase.
- No skin effect on car physics or model behavior.
