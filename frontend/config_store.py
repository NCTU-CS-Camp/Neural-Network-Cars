from __future__ import annotations

import json
from pathlib import Path

from backend.settings import PROJECT_ROOT
from shared.contracts import RuntimeSettings


SETTINGS_PATH = PROJECT_ROOT / "settings.json"


def load_runtime_settings(path: Path = SETTINGS_PATH) -> RuntimeSettings:
    if not path.exists():
        settings = RuntimeSettings()
        save_runtime_settings(settings, path)
        return settings

    data = json.loads(path.read_text(encoding="utf-8"))
    return RuntimeSettings.from_dict(data)


def save_runtime_settings(
    settings: RuntimeSettings, path: Path = SETTINGS_PATH
) -> None:
    path.write_text(json.dumps(settings.to_dict(), indent=2), encoding="utf-8")

