from __future__ import annotations

import json
from pathlib import Path

from game_engine.backend.settings import PROJECT_ROOT
from shared.contracts import LoginProfile


PROFILE_PATH = PROJECT_ROOT / "profile.json"


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


def clear_login_profile(path: Path = PROFILE_PATH) -> None:
    path.unlink(missing_ok=True)
