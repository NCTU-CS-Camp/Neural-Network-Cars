from __future__ import annotations

import json
from pathlib import Path

from game_engine.backend.settings import OFFICIAL_TRACKS_DIR
from game_engine.backend.track_generator import render_track_layout
from game_engine.backend.track_layout import (
    build_boundary_checkpoints,
    generate_track_layout,
)
from server.official_maps import DEFAULT_OFFICIAL_MAP_IDS


OFFICIAL_TRACK_SEEDS = {
    "official_001": 1001,
    "official_002": 2002,
    "official_003": 3003,
    "official_004": 4004,
    "official_005": 5005,
}


def generate_official_tracks(
    output_dir: Path = OFFICIAL_TRACKS_DIR,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for map_id in DEFAULT_OFFICIAL_MAP_IDS:
        seed = OFFICIAL_TRACK_SEEDS[map_id]
        written.extend(_generate_track(output_dir, map_id, seed))
    return written


def _generate_track(
    output_dir: Path,
    map_id: str,
    seed: int,
) -> list[Path]:
    layout = generate_track_layout(seed)
    front_name = f"{map_id}_front.png"
    back_name = f"{map_id}_back.png"
    metadata_name = f"{map_id}.json"
    front_path = output_dir / front_name
    back_path = output_dir / back_name
    metadata_path = output_dir / metadata_name

    render_track_layout(
        layout,
        front_path=front_path,
        back_path=back_path,
    )
    metadata_path.write_text(
        json.dumps(
            {
                "map_id": map_id,
                "name": f"Official Track {int(map_id.rsplit('_', 1)[-1])}",
                "seed": seed,
                "front_path": front_name,
                "back_path": back_name,
                "spawn": layout.spawn,
                "route_cells": [
                    [cell[0], cell[1]] for cell in layout.route_cells
                ],
                "checkpoints": build_boundary_checkpoints(
                    layout,
                    back_path,
                ),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return [front_path, back_path, metadata_path]


def main() -> None:
    written = generate_official_tracks()
    print(
        f"Generated {len(written)} official track files in "
        f"{OFFICIAL_TRACKS_DIR}"
    )


if __name__ == "__main__":
    main()
