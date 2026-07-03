from __future__ import annotations

import json
from pathlib import Path

from game_engine.backend.settings import OFFICIAL_TRACKS_DIR, PROJECT_ROOT
from server.models import OfficialMap


DEFAULT_OFFICIAL_MAP_IDS = [
    "official_001",
    "official_002",
    "official_003",
    "official_004",
    "official_005",
]


def official_map_metadata_path(map_id: str) -> Path:
    return OFFICIAL_TRACKS_DIR / f"{map_id}.json"


def load_official_map(map_id: str) -> OfficialMap:
    path = official_map_metadata_path(map_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["metadata_path"] = _relative_to_project(path)
    data["front_path"] = _relative_to_project(OFFICIAL_TRACKS_DIR / data["front_path"])
    data["back_path"] = _relative_to_project(OFFICIAL_TRACKS_DIR / data["back_path"])
    return OfficialMap.from_metadata(data)


def list_official_maps() -> list[OfficialMap]:
    maps = []
    for map_id in DEFAULT_OFFICIAL_MAP_IDS:
        path = official_map_metadata_path(map_id)
        if path.exists():
            maps.append(load_official_map(map_id))
    return maps


def get_default_map_id() -> str:
    maps = list_official_maps()
    return maps[0].map_id if maps else DEFAULT_OFFICIAL_MAP_IDS[0]


def _relative_to_project(path: Path) -> str:
    return str(path.resolve().relative_to(PROJECT_ROOT))
