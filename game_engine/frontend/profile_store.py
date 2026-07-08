from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from game_engine.backend.settings import USER_DATA_DIR
from shared.contracts import LoginProfile


PROFILE_PATH = USER_DATA_DIR / "profile.json"


def load_login_profile(path: Path = PROFILE_PATH) -> LoginProfile | None:
    if not path.exists():
        return None

    content = path.read_text(encoding="utf-8")
    if not content.strip():
        return None

    try:
        data = json.loads(content)
        return LoginProfile.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def save_login_profile(profile: LoginProfile, path: Path = PROFILE_PATH) -> None:
    path.write_text(json.dumps(profile.to_dict(), indent=2), encoding="utf-8")


def login_session_is_valid(
    profile: LoginProfile,
    *,
    now: datetime | None = None,
) -> bool:
    if not profile.token or not profile.expires_at:
        return False
    try:
        expires_at = datetime.fromisoformat(
            profile.expires_at.replace("Z", "+00:00")
        )
    except ValueError:
        return False
    if expires_at.tzinfo is None:
        return False
    return expires_at > (now or datetime.now(UTC))


def clear_login_profile(path: Path = PROFILE_PATH) -> None:
    path.unlink(missing_ok=True)
