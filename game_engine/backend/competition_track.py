from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from game_engine.backend.settings import PROJECT_ROOT
from game_engine.backend.track_layout import (
    BLOCK_SIZE,
    DIRECTION_DELTAS,
    OPPOSITE_DIRECTION,
    TILE_NAMES,
    TrackLayout,
    build_boundary_checkpoints,
    direction_between,
)


TILE_CONNECTIONS = {tile_name: connections for connections, tile_name in TILE_NAMES.items()}
MAPS_ROOT = PROJECT_ROOT / "maps"
MAP_SUBDIRS = ("train_maps", "valid_maps", "kaggle_maps")
SEGMENT_TOLERANCE_PX = 2.0


@dataclass(frozen=True, slots=True)
class CompetitionTrackMetadata:
    metadata_path: Path
    route_cells: tuple[tuple[int, int], ...]
    checkpoints: tuple[dict[str, Any], ...]
    total_length_px: float


@dataclass(slots=True)
class CompetitionRunTracker:
    checkpoints: tuple[dict[str, Any], ...]
    total_length_px: float
    next_index: int = 0
    checkpoints_completed: int = 0
    completed: bool = False
    lap_ticks: int | None = None
    max_progress: float = 0.0
    ticks_to_max_progress: int = 0
    awaiting_start_gate: bool = False

    @classmethod
    def from_metadata_path(cls, metadata_path: Path | str) -> "CompetitionRunTracker":
        metadata = load_competition_track_metadata(Path(metadata_path))
        return cls(
            checkpoints=metadata.checkpoints,
            total_length_px=metadata.total_length_px,
        )

    def advance(
        self,
        previous: tuple[float, float],
        current: tuple[float, float],
        *,
        tick: int,
    ) -> None:
        if self.completed or not self.checkpoints:
            return

        if self.awaiting_start_gate:
            if _passed_gate(previous, current, self.checkpoints[0]):
                self.checkpoints_completed += 1
                self.completed = True
                self.lap_ticks = tick
                self.awaiting_start_gate = False
                self.max_progress = self.total_length_px
                self.ticks_to_max_progress = tick
            return

        for _ in range(len(self.checkpoints)):
            checkpoint = self.checkpoints[self.next_index]
            if not _passed_gate(previous, current, checkpoint):
                break
            self.checkpoints_completed += 1
            self.next_index += 1
            progress = self._progress_after_checkpoint()
            self._observe_progress(progress, tick=tick)
            if self.next_index >= len(self.checkpoints):
                self.awaiting_start_gate = True
                self.next_index = 0
                break

    def _progress_after_checkpoint(self) -> float:
        required_gate_count = len(self.checkpoints) + 1
        return min(
            self.total_length_px,
            self.total_length_px * self.checkpoints_completed / required_gate_count,
        )

    def _observe_progress(self, progress: float, *, tick: int) -> None:
        if progress > self.max_progress:
            self.max_progress = progress
            self.ticks_to_max_progress = tick


def load_competition_track_metadata(metadata_path: Path) -> CompetitionTrackMetadata:
    data = json.loads(metadata_path.read_text(encoding="utf-8"))
    route_cells = data.get("route_cells")
    checkpoints = data.get("checkpoints")
    if route_cells is None or checkpoints is None:
        route = reconstruct_route_cells(data)
        checkpoints = build_map_boundary_checkpoints(metadata_path, route)
    else:
        route = [(int(cell[0]), int(cell[1])) for cell in route_cells]
    metrics = data.get("metrics", {})
    return CompetitionTrackMetadata(
        metadata_path=metadata_path,
        route_cells=tuple(route),
        checkpoints=tuple(dict(checkpoint) for checkpoint in checkpoints),
        total_length_px=float(metrics.get("total_length_px", len(route) * BLOCK_SIZE)),
    )


def enrich_map_metadata(metadata_path: Path) -> bool:
    data = json.loads(metadata_path.read_text(encoding="utf-8"))
    route = reconstruct_route_cells(data)
    checkpoints = build_map_boundary_checkpoints(metadata_path, route)
    changed = (
        data.get("route_cells") != [[cell[0], cell[1]] for cell in route]
        or data.get("checkpoints") != checkpoints
    )
    data["route_cells"] = [[cell[0], cell[1]] for cell in route]
    data["checkpoints"] = checkpoints
    metadata_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return changed


def iter_map_metadata_paths(root: Path = MAPS_ROOT) -> list[Path]:
    paths: list[Path] = []
    for subdir in MAP_SUBDIRS:
        paths.extend(sorted((root / subdir).glob("*.json")))
    return paths


def reconstruct_route_cells(data: dict[str, Any]) -> list[tuple[int, int]]:
    tiles = {
        (int(tile["x"]), int(tile["y"])): str(tile["tile"])
        for tile in data["tiles"]
    }
    start = (int(data["start"]["x"]), int(data["start"]["y"]))
    finish = (int(data["finish"]["x"]), int(data["finish"]["y"]))
    if start not in tiles:
        raise ValueError(f"start cell is not a road tile: {start}")
    if finish not in tiles:
        raise ValueError(f"finish cell is not a road tile: {finish}")

    away_from_finish = (
        start[0] - finish[0],
        start[1] - finish[1],
    )
    first = (start[0] + away_from_finish[0], start[1] + away_from_finish[1])
    if first not in tiles:
        raise ValueError(f"route cannot leave start away from finish: {start} -> {first}")

    route = [start]
    previous = start
    current = first
    visited = {start}
    while True:
        if current in visited:
            raise ValueError(f"route looped before returning to start: {current}")
        route.append(current)
        visited.add(current)
        neighbours = [
            neighbour
            for neighbour in _connected_neighbours(current, tiles, start, finish)
            if neighbour != previous
        ]
        if len(neighbours) != 1:
            raise ValueError(f"expected one forward neighbour at {current}, got {neighbours}")
        following = neighbours[0]
        if following == start:
            break
        previous, current = current, following

    expected_count = int(data.get("metrics", {}).get("route_cells", len(route)))
    if len(route) != expected_count:
        raise ValueError(
            f"route length mismatch: reconstructed {len(route)}, expected {expected_count}"
        )
    return route


def build_map_boundary_checkpoints(
    metadata_path: Path,
    route: list[tuple[int, int]],
) -> list[dict[str, Any]]:
    layout = TrackLayout(seed=0, route_cells=tuple(route))
    return build_boundary_checkpoints(layout, _back_path_for(metadata_path))


def _connected_neighbours(
    cell: tuple[int, int],
    tiles: dict[tuple[int, int], str],
    start: tuple[int, int],
    finish: tuple[int, int],
) -> list[tuple[int, int]]:
    neighbours = []
    for direction in _connections_for_cell(cell, tiles, start, finish):
        dx, dy = DIRECTION_DELTAS[direction]
        neighbour = (cell[0] + dx, cell[1] + dy)
        if neighbour in tiles:
            neighbours.append(neighbour)
    return neighbours


def _connections_for_cell(
    cell: tuple[int, int],
    tiles: dict[tuple[int, int], str],
    start: tuple[int, int],
    finish: tuple[int, int],
) -> frozenset[str]:
    tile_name = tiles[cell]
    if tile_name == "Initial":
        finish_direction = direction_between(start, finish)
        return frozenset((finish_direction, OPPOSITE_DIRECTION[finish_direction]))
    try:
        return TILE_CONNECTIONS[tile_name]
    except KeyError as exc:
        raise ValueError(f"unsupported tile {tile_name} at {cell}") from exc


def _back_path_for(metadata_path: Path) -> Path:
    return metadata_path.with_name(f"{metadata_path.stem}_back.png")


def _passed_gate(
    previous: tuple[float, float],
    current: tuple[float, float],
    checkpoint: dict[str, Any],
) -> bool:
    a = (float(checkpoint["a"][0]), float(checkpoint["a"][1]))
    b = (float(checkpoint["b"][0]), float(checkpoint["b"][1]))
    return _segments_cross(previous, current, a, b) or (
        _segment_distance(previous, current, a, b) <= SEGMENT_TOLERANCE_PX
    )


def _segments_cross(
    p1: tuple[float, float],
    p2: tuple[float, float],
    q1: tuple[float, float],
    q2: tuple[float, float],
) -> bool:
    o1 = _orientation(p1, p2, q1)
    o2 = _orientation(p1, p2, q2)
    o3 = _orientation(q1, q2, p1)
    o4 = _orientation(q1, q2, p2)
    if o1 * o2 < 0 and o3 * o4 < 0:
        return True
    return (
        (o1 == 0 and _on_segment(p1, q1, p2))
        or (o2 == 0 and _on_segment(p1, q2, p2))
        or (o3 == 0 and _on_segment(q1, p1, q2))
        or (o4 == 0 and _on_segment(q1, p2, q2))
    )


def _orientation(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
) -> float:
    value = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    if abs(value) < 1e-9:
        return 0.0
    return value


def _on_segment(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
) -> bool:
    return (
        min(a[0], c[0]) - 1e-9 <= b[0] <= max(a[0], c[0]) + 1e-9
        and min(a[1], c[1]) - 1e-9 <= b[1] <= max(a[1], c[1]) + 1e-9
    )


def _segment_distance(
    p1: tuple[float, float],
    p2: tuple[float, float],
    q1: tuple[float, float],
    q2: tuple[float, float],
) -> float:
    return min(
        _point_segment_distance(p1, q1, q2),
        _point_segment_distance(p2, q1, q2),
        _point_segment_distance(q1, p1, p2),
        _point_segment_distance(q2, p1, p2),
    )


def _point_segment_distance(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return ((point[0] - start[0]) ** 2 + (point[1] - start[1]) ** 2) ** 0.5
    t = max(
        0.0,
        min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_sq),
    )
    projection = (start[0] + t * dx, start[1] + t * dy)
    return ((point[0] - projection[0]) ** 2 + (point[1] - projection[1]) ** 2) ** 0.5


def main() -> None:
    parser = argparse.ArgumentParser(description="Add route/checkpoint metadata to maps.")
    parser.add_argument("--check", action="store_true", help="Validate without writing.")
    args = parser.parse_args()
    changed = []
    for path in iter_map_metadata_paths():
        if args.check:
            data = json.loads(path.read_text(encoding="utf-8"))
            route = reconstruct_route_cells(data)
            build_map_boundary_checkpoints(path, route)
            continue
        if enrich_map_metadata(path):
            changed.append(path)
    if changed:
        print("Updated map metadata:")
        for path in changed:
            print(f"- {path}")
    else:
        print("Map metadata already up to date.")


if __name__ == "__main__":
    main()
