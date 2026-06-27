from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pygame

from game_engine.backend.settings import PROJECT_ROOT, SCREEN_SIZE, TRACK_ASSETS_DIR
from game_engine.backend.track_layout import angle_for_vector, cell_center, cell_origin
from server.models import CompetitionId


MAPS_DIR = PROJECT_ROOT / "maps"


@dataclass(frozen=True, slots=True)
class CompetitionMap:
    competition_id: CompetitionId
    map_id: str
    name: str
    metadata_path: Path
    front_path: Path
    start_cell: tuple[int, int]
    finish_cell: tuple[int, int]
    total_length_px: float

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
        """Recreate the transparent road layer without altering source map PNGs."""
        metadata = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        surface = pygame.Surface(SCREEN_SIZE, pygame.SRCALPHA)
        surface.fill((0, 0, 0, 0))

        for tile in metadata["tiles"]:
            tile_name = str(tile["tile"])
            if tile_name == "Initial":
                tile_name = self._initial_collision_tile()
            road_tile = pygame.image.load(TRACK_ASSETS_DIR / f"{tile_name}.png")
            origin = cell_origin((int(tile["x"]), int(tile["y"])))
            surface.blit(road_tile, origin)
        return surface

    def _initial_collision_tile(self) -> str:
        if self.start_cell[0] == self.finish_cell[0]:
            return "Straight2"
        return "Straight1"


_MAP_FILES = {
    CompetitionId.EASY: "kaggle_easy",
    CompetitionId.HARD: "kaggle_hard",
    CompetitionId.FINAL: "kaggle_final",
}


def get_competition_map(competition_id: CompetitionId | str) -> CompetitionMap:
    identifier = CompetitionId(competition_id)
    map_id = _MAP_FILES[identifier]
    metadata_path = MAPS_DIR / f"{map_id}.json"
    data = json.loads(metadata_path.read_text(encoding="utf-8"))
    metrics = data.get("metrics", {})
    return CompetitionMap(
        competition_id=identifier,
        map_id=map_id,
        name=str(data["name"]),
        metadata_path=metadata_path,
        front_path=MAPS_DIR / f"{map_id}.png",
        start_cell=(int(data["start"]["x"]), int(data["start"]["y"])),
        finish_cell=(int(data["finish"]["x"]), int(data["finish"]["y"])),
        total_length_px=float(metrics.get("total_length_px", 0.0)),
    )


def list_competition_maps() -> list[CompetitionMap]:
    return [get_competition_map(identifier) for identifier in CompetitionId]
