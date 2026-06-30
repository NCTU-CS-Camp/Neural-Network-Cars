from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


Cell = tuple[int, int]
Point = tuple[float, float]

TILE_CONNECTIONS: dict[str, tuple[str, str]] = {
    "Straight1": ("E", "W"),
    "Straight2": ("N", "S"),
    "Curve1": ("S", "E"),
    "Curve2": ("W", "S"),
    "Curve3": ("N", "W"),
    "Curve4": ("E", "N"),
    "Initial": ("N", "S"),
}

DIRECTION_OFFSETS: dict[str, Cell] = {
    "N": (0, -1),
    "S": (0, 1),
    "E": (1, 0),
    "W": (-1, 0),
}

OPPOSITE_DIRECTIONS = {"N": "S", "S": "N", "E": "W", "W": "E"}


@dataclass(frozen=True, slots=True)
class TrackProjection:
    progress: float
    center_offset: float
    segment_index: int
    target_heading: float


@dataclass(frozen=True, slots=True)
class TrackGeometry:
    centerline: tuple[Point, ...]
    half_width: float
    segment_lengths: tuple[float, ...]
    cumulative_lengths: tuple[float, ...]
    total_length: float

    @classmethod
    def from_json(
        cls,
        path: Path,
        *,
        default_half_width: float,
    ) -> TrackGeometry:
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_map_data(data, default_half_width=default_half_width)

    @classmethod
    def from_map_data(
        cls,
        data: dict[str, Any],
        *,
        default_half_width: float,
    ) -> TrackGeometry:
        grid = data["grid"]
        tiles_by_cell = {
            (int(tile["x"]), int(tile["y"])): str(tile["tile"])
            for tile in data["tiles"]
        }
        start = (int(data["start"]["x"]), int(data["start"]["y"]))
        finish = (int(data["finish"]["x"]), int(data["finish"]["y"]))
        ordered_cells = _order_closed_route(
            tiles_by_cell,
            start=start,
            finish=finish,
        )

        cell_size = float(grid["cell_size"])
        offset_x = float(grid["offset_x"])
        offset_y = float(grid["offset_y"])
        centerline = tuple(
            (
                offset_x + (cell_x * cell_size) + (cell_size / 2.0),
                offset_y + (cell_y * cell_size) + (cell_size / 2.0),
            )
            for cell_x, cell_y in ordered_cells
        )
        half_width = float(data.get("half_width_px", default_half_width))
        return cls.from_centerline(centerline, half_width=half_width)

    @classmethod
    def from_centerline(
        cls,
        centerline: tuple[Point, ...],
        *,
        half_width: float,
    ) -> TrackGeometry:
        if len(centerline) < 3:
            raise ValueError("A closed track requires at least three centerline points")
        if half_width <= 0:
            raise ValueError("Track half_width must be positive")

        segment_lengths = []
        cumulative_lengths = []
        total_length = 0.0
        for index, start in enumerate(centerline):
            end = centerline[(index + 1) % len(centerline)]
            segment_length = math.dist(start, end)
            if segment_length <= 0:
                raise ValueError("Track centerline contains a zero-length segment")
            cumulative_lengths.append(total_length)
            segment_lengths.append(segment_length)
            total_length += segment_length

        return cls(
            centerline=centerline,
            half_width=half_width,
            segment_lengths=tuple(segment_lengths),
            cumulative_lengths=tuple(cumulative_lengths),
            total_length=total_length,
        )

    def project(self, point: Point) -> TrackProjection:
        best_distance = math.inf
        best_progress = 0.0
        best_segment_index = 0
        best_target_heading = 0.0

        for index, start in enumerate(self.centerline):
            end = self.centerline[(index + 1) % len(self.centerline)]
            dx = end[0] - start[0]
            dy = end[1] - start[1]
            length_squared = (dx * dx) + (dy * dy)
            relative_x = point[0] - start[0]
            relative_y = point[1] - start[1]
            raw_t = ((relative_x * dx) + (relative_y * dy)) / length_squared
            t = min(1.0, max(0.0, raw_t))
            projection_x = start[0] + (t * dx)
            projection_y = start[1] + (t * dy)
            distance = math.dist(point, (projection_x, projection_y))

            if distance < best_distance:
                best_distance = distance
                best_progress = (
                    self.cumulative_lengths[index]
                    + (self.segment_lengths[index] * t)
                )
                best_segment_index = index
                best_target_heading = (-math.degrees(math.atan2(dx, dy))) % 360.0

        return TrackProjection(
            progress=best_progress,
            center_offset=best_distance,
            segment_index=best_segment_index,
            target_heading=best_target_heading,
        )

    def contains(self, point: Point) -> bool:
        return self.project(point).center_offset <= self.half_width


def _order_closed_route(
    tiles_by_cell: dict[Cell, str],
    *,
    start: Cell,
    finish: Cell,
) -> tuple[Cell, ...]:
    cells = set(tiles_by_cell)
    if start not in cells:
        raise ValueError("Track start cell is missing from tiles")
    if finish not in cells:
        raise ValueError("Track finish cell is missing from tiles")

    adjacency: dict[Cell, tuple[Cell, ...]] = {}
    for cell, tile_name in tiles_by_cell.items():
        try:
            connections = TILE_CONNECTIONS[tile_name]
        except KeyError as error:
            raise ValueError(f"Unsupported track tile: {tile_name}") from error

        connected_neighbours = []
        for direction in connections:
            offset_x, offset_y = DIRECTION_OFFSETS[direction]
            neighbour = (cell[0] + offset_x, cell[1] + offset_y)
            neighbour_tile = tiles_by_cell.get(neighbour)
            if neighbour_tile is None:
                continue
            neighbour_connections = TILE_CONNECTIONS.get(neighbour_tile)
            if neighbour_connections is None:
                raise ValueError(f"Unsupported track tile: {neighbour_tile}")
            if OPPOSITE_DIRECTIONS[direction] in neighbour_connections:
                connected_neighbours.append(neighbour)
        adjacency[cell] = tuple(connected_neighbours)
    invalid_cells = [cell for cell, neighbours in adjacency.items() if len(neighbours) != 2]
    if invalid_cells:
        raise ValueError(
            "Track tiles must form one closed route; invalid cells: "
            f"{sorted(invalid_cells)}"
        )
    if finish not in adjacency[start]:
        raise ValueError("Track finish must be the cell immediately behind the start")

    ordered = [start]
    previous = finish
    current = start
    while True:
        next_cell = next(
            neighbour
            for neighbour in adjacency[current]
            if neighbour != previous
        )
        if next_cell == start:
            break
        if next_cell in ordered:
            raise ValueError("Track tiles contain a disconnected or repeated loop")
        ordered.append(next_cell)
        previous, current = current, next_cell

    if len(ordered) != len(cells):
        raise ValueError("Track tiles contain more than one closed route")
    if ordered[-1] != finish:
        raise ValueError("Track route direction does not end at the finish cell")
    return tuple(ordered)
