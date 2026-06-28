from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from pathlib import Path


Point = tuple[float, float]
CellCoord = tuple[int, int]
Segment = tuple[float, float, float, float, float, float, float]

TILE_CONNECTIONS: dict[str, tuple[str, str]] = {
    "Straight1": ("E", "W"),
    "Straight2": ("N", "S"),
    "Curve1": ("S", "E"),
    "Curve2": ("W", "S"),
    "Curve3": ("N", "W"),
    "Curve4": ("E", "N"),
    "Initial": ("N", "S"),
}
DIRS: dict[str, tuple[int, int, str]] = {
    "N": (0, -1, "S"),
    "E": (1, 0, "W"),
    "S": (0, 1, "N"),
    "W": (-1, 0, "E"),
}


@dataclass(frozen=True, slots=True)
class TrackGeometry:
    polyline: tuple[Point, ...]
    total_length: float
    start_position: Point
    start_angle: float
    half_width: float
    canvas_size: tuple[int, int]
    map_name: str
    _segments: tuple[Segment, ...] = field(
        init=False,
        repr=False,
        compare=False,
    )
    _half_width_sq: float = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        traversed = 0.0
        segments: list[Segment] = []
        for start, end in zip(self.polyline[:-1], self.polyline[1:]):
            vx = end[0] - start[0]
            vy = end[1] - start[1]
            length_sq = (vx * vx) + (vy * vy)
            if length_sq == 0:
                continue
            length = math.sqrt(length_sq)
            segments.append(
                (
                    start[0],
                    start[1],
                    vx,
                    vy,
                    length_sq,
                    length,
                    traversed,
                )
            )
            traversed += length
        if not segments:
            raise ValueError("Track route has no usable segments")
        object.__setattr__(self, "_segments", tuple(segments))
        object.__setattr__(self, "_half_width_sq", self.half_width**2)

    @classmethod
    def from_route_cells(
        cls,
        route_cells: list[CellCoord] | tuple[CellCoord, ...],
        *,
        cell_size: int = 146,
        offset_x: int = 70,
        offset_y: int = 85,
        half_width: float = 34.0,
        canvas_size: tuple[int, int] = (1600, 900),
        map_name: str = "generated",
    ) -> "TrackGeometry":
        polyline = tuple(
            (
                offset_x + (x * cell_size) + (cell_size / 2),
                offset_y + (y * cell_size) + (cell_size / 2),
            )
            for x, y in route_cells
        )
        if len(polyline) < 2:
            raise ValueError("Track route needs at least two cells")
        total_length = sum(
            math.dist(start, end)
            for start, end in zip(polyline[:-1], polyline[1:])
        )
        if total_length <= 0:
            raise ValueError("Track route has no length")
        start = polyline[0]
        following = polyline[1]
        dx = following[0] - start[0]
        dy = following[1] - start[1]
        start_angle = (-math.degrees(math.atan2(dx, dy))) % 360
        return cls(
            polyline=polyline,
            total_length=total_length,
            start_position=start,
            start_angle=start_angle,
            half_width=half_width,
            canvas_size=canvas_size,
            map_name=map_name,
        )

    def project(self, point: Point) -> tuple[float, float]:
        best_progress = 0.0
        best_distance_sq = float("inf")
        for start_x, start_y, vx, vy, length_sq, length, traversed in self._segments:
            ux = point[0] - start_x
            uy = point[1] - start_y
            ratio = max(
                0.0,
                min(1.0, ((ux * vx) + (uy * vy)) / length_sq),
            )
            dx = point[0] - (start_x + (vx * ratio))
            dy = point[1] - (start_y + (vy * ratio))
            distance_sq = (dx * dx) + (dy * dy)
            if distance_sq < best_distance_sq:
                best_distance_sq = distance_sq
                best_progress = traversed + (length * ratio)
        return best_progress, math.sqrt(best_distance_sq)

    def heading_at_progress(self, progress: float) -> float:
        remaining = max(0.0, min(progress, self.total_length))
        for _, _, vx, vy, _, length, _ in self._segments:
            if remaining <= length:
                return (-math.degrees(math.atan2(vx, vy))) % 360
            remaining -= length
        _, _, vx, vy, _, _, _ = self._segments[-1]
        return (-math.degrees(math.atan2(vx, vy))) % 360

    def is_on_track(self, point: Point) -> bool:
        for start_x, start_y, vx, vy, length_sq, _, _ in self._segments:
            ux = point[0] - start_x
            uy = point[1] - start_y
            ratio = max(
                0.0,
                min(1.0, ((ux * vx) + (uy * vy)) / length_sq),
            )
            dx = point[0] - (start_x + (vx * ratio))
            dy = point[1] - (start_y + (vy * ratio))
            if ((dx * dx) + (dy * dy)) <= self._half_width_sq:
                return True
        return False


def load_track_geometry(
    path: str | Path,
    *,
    half_width: float = 34.0,
) -> TrackGeometry:
    metadata_path = Path(path)
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    grid = payload["grid"]
    canvas = payload["canvas"]
    tiles = {
        (int(item["x"]), int(item["y"])): str(item["tile"])
        for item in payload["tiles"]
    }
    start = (int(payload["start"]["x"]), int(payload["start"]["y"]))
    finish = (int(payload["finish"]["x"]), int(payload["finish"]["y"]))
    topology = str(payload.get("metrics", {}).get("topology", ""))
    route = _ordered_route(tiles, start, finish, topology)
    return TrackGeometry.from_route_cells(
        route,
        cell_size=int(grid["cell_size"]),
        offset_x=int(grid["offset_x"]),
        offset_y=int(grid["offset_y"]),
        half_width=half_width,
        canvas_size=(int(canvas["width"]), int(canvas["height"])),
        map_name=str(payload.get("name", metadata_path.stem)),
    )


def _connected_neighbors(
    cell: CellCoord,
    tiles: dict[CellCoord, str],
) -> list[CellCoord]:
    try:
        connections = TILE_CONNECTIONS[tiles[cell]]
    except KeyError as exc:
        raise ValueError(f"Unsupported track tile at {cell}") from exc
    neighbors: list[CellCoord] = []
    for direction in connections:
        dx, dy, opposite = DIRS[direction]
        neighbor = (cell[0] + dx, cell[1] + dy)
        neighbor_tile = tiles.get(neighbor)
        if neighbor_tile and opposite in TILE_CONNECTIONS[neighbor_tile]:
            neighbors.append(neighbor)
    return neighbors


def _ordered_route(
    tiles: dict[CellCoord, str],
    start: CellCoord,
    finish: CellCoord,
    topology: str,
) -> list[CellCoord]:
    if topology != "closed_circuit":
        return _open_route(tiles, start, finish)
    start_neighbors = _connected_neighbors(start, tiles)
    if len(start_neighbors) != 2:
        raise ValueError("Closed track start must connect to two neighbors")
    routes = [
        _trace_to_finish(tiles, start, neighbor, finish)
        for neighbor in start_neighbors
    ]
    route = max(routes, key=len)
    if len(route) != len(tiles):
        raise ValueError("Closed track route does not cover every road tile")
    return route


def _trace_to_finish(
    tiles: dict[CellCoord, str],
    start: CellCoord,
    first: CellCoord,
    finish: CellCoord,
) -> list[CellCoord]:
    route = [start]
    previous = start
    current = first
    visited = {start}
    while True:
        if current in visited:
            raise ValueError("Track looped before reaching finish")
        route.append(current)
        visited.add(current)
        if current == finish:
            return route
        candidates = [
            neighbor
            for neighbor in _connected_neighbors(current, tiles)
            if neighbor != previous
        ]
        if len(candidates) != 1:
            raise ValueError(f"Track branches or ends at {current}")
        previous, current = current, candidates[0]


def _open_route(
    tiles: dict[CellCoord, str],
    start: CellCoord,
    finish: CellCoord,
) -> list[CellCoord]:
    previous: dict[CellCoord, CellCoord | None] = {start: None}
    queue = [start]
    for current in queue:
        if current == finish:
            break
        for neighbor in _connected_neighbors(current, tiles):
            if neighbor not in previous:
                previous[neighbor] = current
                queue.append(neighbor)
    if finish not in previous:
        raise ValueError("Finish is not reachable from start")
    route: list[CellCoord] = []
    cursor: CellCoord | None = finish
    while cursor is not None:
        route.append(cursor)
        cursor = previous[cursor]
    route.reverse()
    return route
