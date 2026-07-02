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
