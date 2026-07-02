from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from game_engine.backend.settings import PROJECT_ROOT
from shared.contracts import DEFAULT_SERVER_URL


ENV_PATH = PROJECT_ROOT / ".env"
SERVER_URL_ENV_VAR = "COMPETITION_SERVER_URL"
DEBUG_ENV_VAR = "DEBUG"


def _read_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {'"', "'"}
        ):
            value = value[1:-1]
        values[name] = value
    return values


def load_server_url(
    path: Path = ENV_PATH,
    environ: Mapping[str, str] | None = None,
) -> str:
    environment = os.environ if environ is None else environ
    server_url = (
        environment.get(SERVER_URL_ENV_VAR)
        or _read_env(path).get(SERVER_URL_ENV_VAR)
        or DEFAULT_SERVER_URL
    ).strip()
    if not server_url.startswith(("http://", "https://")):
        raise ValueError(
            f"{SERVER_URL_ENV_VAR} must start with http:// or https://"
        )
    return server_url.rstrip("/")


def load_debug_mode(
    path: Path = ENV_PATH,
    environ: Mapping[str, str] | None = None,
) -> bool:
    environment = os.environ if environ is None else environ
    value = (
        environment.get(DEBUG_ENV_VAR)
        or _read_env(path).get(DEBUG_ENV_VAR)
        or "0"
    ).strip()
    if value not in {"0", "1"}:
        raise ValueError(f"{DEBUG_ENV_VAR} must be 0 or 1")
    return value == "1"
