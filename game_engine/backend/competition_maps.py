from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from game_engine.backend.competition_track import CompetitionRunTracker, load_competition_track_metadata
from game_engine.backend.settings import MAPS_DIR, VALID_MAPS_DIR
from game_engine.backend.track_layout import angle_for_vector, cell_center


KAGGLE_MAPS_DIR = MAPS_DIR / "kaggle_maps"


@dataclass(frozen=True, slots=True)
class CompetitionMap:
    competition_id: str
    front_path: Path
    back_path: Path
    spawn: dict[str, float]
    metadata_path: Path

    def new_tracker(self) -> CompetitionRunTracker:
        metadata = load_competition_track_metadata(self.metadata_path)
        return CompetitionRunTracker(
            checkpoints=metadata.checkpoints,
            total_length_px=metadata.total_length_px,
        )


def _load_scoring_map(
    competition_id: str, front_path: Path, back_path: Path, metadata_path: Path
) -> CompetitionMap:
    metadata = load_competition_track_metadata(metadata_path)

    start_cell = metadata.route_cells[0]
    next_cell = metadata.route_cells[1]
    start_x, start_y = cell_center(start_cell)
    next_x, next_y = cell_center(next_cell)
    spawn = {
        "x": start_x,
        "y": start_y,
        "angle": angle_for_vector(next_x - start_x, next_y - start_y),
    }

    return CompetitionMap(
        competition_id=competition_id,
        front_path=front_path,
        back_path=back_path,
        spawn=spawn,
        metadata_path=metadata_path,
    )


def load_competition_map(competition_id: str) -> CompetitionMap:
    stem = f"kaggle_{competition_id}"
    return _load_scoring_map(
        competition_id,
        front_path=KAGGLE_MAPS_DIR / f"{stem}.png",
        back_path=KAGGLE_MAPS_DIR / f"{stem}_back.png",
        metadata_path=KAGGLE_MAPS_DIR / f"{stem}.json",
    )


def load_validation_map(map_id: str) -> CompetitionMap:
    stem = f"valid_{map_id}"
    return _load_scoring_map(
        map_id,
        front_path=VALID_MAPS_DIR / f"{stem}.png",
        back_path=VALID_MAPS_DIR / f"{stem}_back.png",
        metadata_path=VALID_MAPS_DIR / f"{stem}.json",
    )
