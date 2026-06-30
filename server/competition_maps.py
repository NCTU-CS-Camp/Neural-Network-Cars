from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pygame

from game_engine.backend.competition_track import load_competition_track_metadata
from game_engine.backend.settings import PROJECT_ROOT
from game_engine.backend.track_layout import angle_for_vector, cell_center
from server.models import CompetitionId


MAPS_DIR = PROJECT_ROOT / "maps"
KAGGLE_MAPS_DIR = MAPS_DIR / "kaggle_maps"


@dataclass(frozen=True, slots=True)
class CompetitionMap:
    competition_id: CompetitionId
    map_id: str
    name: str
    metadata_path: Path
    front_path: Path
    back_path: Path
    start_cell: tuple[int, int]
    finish_cell: tuple[int, int]
    total_length_px: float
    route_cells: tuple[tuple[int, int], ...]
    checkpoints: tuple[dict[str, Any], ...]

    @property
    def spawn(self) -> dict[str, float]:
        x, y = cell_center(self.start_cell)
        dx = self.start_cell[0] - self.finish_cell[0]
        dy = self.start_cell[1] - self.finish_cell[1]
        if abs(dx) + abs(dy) != 1:
            raise ValueError(
                f"{self.map_id} finish must be adjacent to start to derive replay spawn"
            )
        return {
            "x": float(x),
            "y": float(y),
            "angle": float(angle_for_vector(dx, dy)),
        }

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "competition_id": self.competition_id.value,
            "map_id": self.map_id,
            "name": self.name,
            "spawn": self.spawn,
            "total_length_px": self.total_length_px,
        }

    def build_collision_surface(self) -> pygame.Surface:
        """Load the authored collision layer for the competition map."""
        return pygame.image.load(self.back_path)


_MAP_FILES = {
    CompetitionId.EASY: "kaggle_easy",
    CompetitionId.HARD: "kaggle_hard",
    CompetitionId.FINAL: "kaggle_final",
}


def get_competition_map(competition_id: CompetitionId | str) -> CompetitionMap:
    identifier = CompetitionId(competition_id)
    map_id = _MAP_FILES[identifier]
    metadata_path = KAGGLE_MAPS_DIR / f"{map_id}.json"
    data = json.loads(metadata_path.read_text(encoding="utf-8"))
    metrics = data.get("metrics", {})
    track_metadata = load_competition_track_metadata(metadata_path)
    return CompetitionMap(
        competition_id=identifier,
        map_id=map_id,
        name=str(data["name"]),
        metadata_path=metadata_path,
        front_path=KAGGLE_MAPS_DIR / f"{map_id}.png",
        back_path=KAGGLE_MAPS_DIR / f"{map_id}_back.png",
        start_cell=(int(data["start"]["x"]), int(data["start"]["y"])),
        finish_cell=(int(data["finish"]["x"]), int(data["finish"]["y"])),
        total_length_px=float(metrics.get("total_length_px", 0.0)),
        route_cells=track_metadata.route_cells,
        checkpoints=track_metadata.checkpoints,
    )


def list_competition_maps() -> list[CompetitionMap]:
    return [get_competition_map(identifier) for identifier in CompetitionId]
