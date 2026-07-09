from __future__ import annotations

import json
from pathlib import Path

from game_engine.backend.settings import IS_FROZEN, PROJECT_ROOT, USER_DATA_DIR
from shared.contracts import RuntimeSettings


SETTINGS_PATH = USER_DATA_DIR / "settings.json"
CLIENT_DEFAULTS_PATH = PROJECT_ROOT / "configs" / "client_defaults.json"


def _default_runtime_settings() -> RuntimeSettings:
    if not CLIENT_DEFAULTS_PATH.exists():
        return RuntimeSettings()
    try:
        data = json.loads(CLIENT_DEFAULTS_PATH.read_text(encoding="utf-8"))
        return RuntimeSettings.from_dict(data)
    except (json.JSONDecodeError, TypeError, ValueError):
        return RuntimeSettings()


def load_runtime_settings(path: Path = SETTINGS_PATH) -> RuntimeSettings:
    if not path.exists():
        settings = _default_runtime_settings()
        save_runtime_settings(settings, path)
        return settings

    data = json.loads(path.read_text(encoding="utf-8"))
    settings = RuntimeSettings.from_dict(data)
    if IS_FROZEN:
        defaults = _default_runtime_settings()
        settings.server_url = defaults.server_url
        settings.population_size = defaults.population_size
    return settings


def save_runtime_settings(
    settings: RuntimeSettings, path: Path = SETTINGS_PATH
) -> None:
    path.write_text(json.dumps(settings.to_dict(), indent=2), encoding="utf-8")
