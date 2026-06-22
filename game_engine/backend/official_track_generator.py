from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

from game_engine.backend.settings import OFFICIAL_TRACKS_DIR, SCREEN_SIZE
from server.official_maps import DEFAULT_OFFICIAL_MAP_IDS


ROAD_WIDTH = 120
CHECKPOINT_COUNT = 18


def generate_official_tracks(output_dir: Path = OFFICIAL_TRACKS_DIR) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for index, map_id in enumerate(DEFAULT_OFFICIAL_MAP_IDS):
        written.extend(_generate_track(output_dir, map_id, index))
    return written


def _generate_track(output_dir: Path, map_id: str, variant: int) -> list[Path]:
    width, height = SCREEN_SIZE
    center_x = 610 + (variant % 2) * 55
    center_y = 430 + (variant % 3) * 22
    radius_x = 455 - (variant % 3) * 28
    radius_y = 265 + (variant % 2) * 30
    wobble = 28 + variant * 5
    phase = variant * 0.7

    points = [
        _track_point(t / 240.0, center_x, center_y, radius_x, radius_y, wobble, phase)
        for t in range(240)
    ]
    closed_points = points + [points[0]]

    back = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    back_draw = ImageDraw.Draw(back)
    back_draw.line(closed_points, fill=(255, 255, 255, 255), width=ROAD_WIDTH, joint="curve")

    front = Image.new("RGBA", (width, height), (21, 29, 37, 255))
    front_draw = ImageDraw.Draw(front)
    front_draw.rectangle((0, 0, width, height), fill=(17, 24, 31, 255))
    front_draw.line(closed_points, fill=(49, 58, 67, 255), width=ROAD_WIDTH + 12, joint="curve")
    front_draw.line(closed_points, fill=(79, 88, 96, 255), width=ROAD_WIDTH - 8, joint="curve")
    front_draw.line(closed_points, fill=(221, 226, 232, 255), width=4, joint="curve")

    checkpoints = _build_checkpoints(points)
    spawn = _build_spawn(points)
    front_draw.ellipse(
        (
            spawn["x"] - 12,
            spawn["y"] - 12,
            spawn["x"] + 12,
            spawn["y"] + 12,
        ),
        fill=(80, 220, 145, 255),
    )

    front_name = f"{map_id}_front.png"
    back_name = f"{map_id}_back.png"
    metadata_name = f"{map_id}.json"
    front_path = output_dir / front_name
    back_path = output_dir / back_name
    metadata_path = output_dir / metadata_name
    front.save(front_path)
    back.save(back_path)
    metadata_path.write_text(
        json.dumps(
            {
                "map_id": map_id,
                "name": f"Official Track {variant + 1}",
                "front_path": front_name,
                "back_path": back_name,
                "spawn": spawn,
                "checkpoints": checkpoints,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return [front_path, back_path, metadata_path]


def _track_point(
    t: float,
    center_x: float,
    center_y: float,
    radius_x: float,
    radius_y: float,
    wobble: float,
    phase: float,
) -> tuple[float, float]:
    angle = math.tau * t
    x = center_x + radius_x * math.cos(angle) + wobble * math.sin(3 * angle + phase)
    y = center_y + radius_y * math.sin(angle) + wobble * math.cos(2 * angle + phase)
    return x, y


def _build_checkpoints(points: list[tuple[float, float]]) -> list[dict]:
    checkpoints = []
    step = len(points) // CHECKPOINT_COUNT
    for index in range(CHECKPOINT_COUNT):
        point_index = index * step
        prev_point = points[(point_index - 2) % len(points)]
        next_point = points[(point_index + 2) % len(points)]
        center = points[point_index]
        tangent = (next_point[0] - prev_point[0], next_point[1] - prev_point[1])
        length = math.hypot(tangent[0], tangent[1]) or 1.0
        normal = (-tangent[1] / length, tangent[0] / length)
        half_gate = ROAD_WIDTH * 0.62
        a = (center[0] + normal[0] * half_gate, center[1] + normal[1] * half_gate)
        b = (center[0] - normal[0] * half_gate, center[1] - normal[1] * half_gate)
        checkpoints.append(
            {
                "index": index,
                "center": [round(center[0], 2), round(center[1], 2)],
                "a": [round(a[0], 2), round(a[1], 2)],
                "b": [round(b[0], 2), round(b[1], 2)],
            }
        )
    return checkpoints


def _build_spawn(points: list[tuple[float, float]]) -> dict:
    spawn_point = points[-4]
    target_point = points[0]
    dx = target_point[0] - spawn_point[0]
    dy = target_point[1] - spawn_point[1]
    rad = math.atan2(dx, dy)
    angle = (-math.degrees(rad)) % 360
    return {
        "x": round(spawn_point[0], 2),
        "y": round(spawn_point[1], 2),
        "angle": round(angle, 2),
    }


def main() -> None:
    written = generate_official_tracks()
    print(f"Generated {len(written)} official track files in {OFFICIAL_TRACKS_DIR}")


if __name__ == "__main__":
    main()
