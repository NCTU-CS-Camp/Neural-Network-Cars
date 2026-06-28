from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import random
from typing import Union


Point = tuple[float, float]
MapRef = Union[int, str, Path]


_DIRECTION_DELTAS = {
    "N": (0, -1),
    "S": (0, 1),
    "E": (1, 0),
    "W": (-1, 0),
}

_OPPOSITE_DIRECTIONS = {"N": "S", "S": "N", "E": "W", "W": "E"}

_TILE_CONNECTIONS = {
    "Initial": ("N", "S"),
    "Straight1": ("E", "W"),
    "Straight2": ("N", "S"),
    "Curve1": ("E", "S"),
    "Curve2": ("W", "S"),
    "Curve3": ("W", "N"),
    "Curve4": ("E", "N"),
}


def _move(point: Point, dx: float, dy: float) -> Point:
    return point[0] + dx, point[1] + dy


@dataclass
class Track:
    seed: int | str
    polyline: list[Point]
    total_length: float
    start_position: Point
    start_angle: float
    cell_size: int
    half_width: float
    canvas_size: tuple[int, int]
    closed_loop: bool = False

    def segments(self) -> list[tuple[Point, Point]]:
        segments = list(zip(self.polyline[:-1], self.polyline[1:]))
        if self.closed_loop and len(self.polyline) > 2:
            segments.append((self.polyline[-1], self.polyline[0]))
        return segments

    def point_at_progress(self, progress: float) -> Point:
        progress = max(0.0, min(progress, self.total_length))
        remaining = progress
        for start, end in self.segments():
            seg_len = math.dist(start, end)
            if remaining <= seg_len:
                if seg_len == 0:
                    return start
                ratio = remaining / seg_len
                return (
                    start[0] + (end[0] - start[0]) * ratio,
                    start[1] + (end[1] - start[1]) * ratio,
                )
            remaining -= seg_len
        return self.polyline[-1]

    def heading_at_progress(self, progress: float) -> float:
        progress = max(0.0, min(progress, self.total_length))
        remaining = progress
        for start, end in self.segments():
            seg_len = math.dist(start, end)
            if remaining <= seg_len:
                dx = end[0] - start[0]
                dy = end[1] - start[1]
                return (-math.degrees(math.atan2(dx, dy))) % 360
            remaining -= seg_len
        start, end = self.segments()[-1]
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        return (-math.degrees(math.atan2(dx, dy))) % 360

    def project(self, point: Point) -> tuple[float, float]:
        best_progress = 0.0
        best_distance = float("inf")
        traversed = 0.0
        for start, end in self.segments():
            vx = end[0] - start[0]
            vy = end[1] - start[1]
            seg_len_sq = (vx * vx) + (vy * vy)
            seg_len = math.sqrt(seg_len_sq)
            if seg_len_sq == 0:
                continue
            ux = point[0] - start[0]
            uy = point[1] - start[1]
            t = max(0.0, min(1.0, ((ux * vx) + (uy * vy)) / seg_len_sq))
            proj = (start[0] + (vx * t), start[1] + (vy * t))
            dist = math.dist(point, proj)
            if dist < best_distance:
                best_distance = dist
                best_progress = traversed + (seg_len * t)
            traversed += seg_len
        return best_progress, best_distance

    def is_on_track(self, point: Point) -> bool:
        _, distance = self.project(point)
        return distance <= self.half_width


def _cell_center(cell_x: int, cell_y: int, cell_size: int, offset_x: int, offset_y: int) -> Point:
    return (
        offset_x + (cell_x * cell_size) + (cell_size / 2),
        offset_y + (cell_y * cell_size) + (cell_size / 2),
    )


def _connected_neighbours(
    cell: tuple[int, int],
    tiles: dict[tuple[int, int], str],
) -> list[tuple[int, int]]:
    tile = tiles[cell]
    neighbours = []
    for direction in _TILE_CONNECTIONS[tile]:
        dx, dy = _DIRECTION_DELTAS[direction]
        neighbour = (cell[0] + dx, cell[1] + dy)
        neighbour_tile = tiles.get(neighbour)
        if not neighbour_tile:
            continue
        if _OPPOSITE_DIRECTIONS[direction] in _TILE_CONNECTIONS[neighbour_tile]:
            neighbours.append(neighbour)
    return neighbours


def _ordered_map_cells(
    tiles: dict[tuple[int, int], str],
    start: tuple[int, int],
    finish: tuple[int, int],
) -> list[tuple[int, int]]:
    ordered = [start]
    previous: tuple[int, int] | None = None
    current = start

    while current != finish or len(ordered) == 1:
        neighbours = _connected_neighbours(current, tiles)
        if previous is None:
            preferred = (current[0], current[1] - 1)
            next_cell = preferred if preferred in neighbours else neighbours[0]
        else:
            candidates = [neighbour for neighbour in neighbours if neighbour != previous]
            if not candidates:
                break
            next_cell = candidates[0]

        previous, current = current, next_cell
        ordered.append(current)
        if len(ordered) > len(tiles) + 1:
            raise ValueError("Map route did not reach finish without looping")

    return ordered


def load_tile_track(path: str | Path, half_width: float = 42.0) -> Track:
    map_path = Path(path)
    with map_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    grid = payload["grid"]
    cell_size = int(grid["cell_size"])
    offset_x = int(grid["offset_x"])
    offset_y = int(grid["offset_y"])
    tiles = {
        (int(item["x"]), int(item["y"])): item["tile"]
        for item in payload["tiles"]
    }
    start = (int(payload["start"]["x"]), int(payload["start"]["y"]))
    finish = (int(payload["finish"]["x"]), int(payload["finish"]["y"]))
    ordered_cells = _ordered_map_cells(tiles=tiles, start=start, finish=finish)
    polyline = [
        _cell_center(cell_x, cell_y, cell_size, offset_x, offset_y)
        for cell_x, cell_y in ordered_cells
    ]

    closed_loop = payload.get("metrics", {}).get("topology") == "closed_circuit"
    total_length = sum(math.dist(start_point, end_point) for start_point, end_point in zip(polyline[:-1], polyline[1:]))
    if closed_loop:
        total_length += math.dist(polyline[-1], polyline[0])
    start_position = polyline[0]
    next_position = polyline[1]
    dx = next_position[0] - start_position[0]
    dy = next_position[1] - start_position[1]
    start_angle = (-math.degrees(math.atan2(dx, dy))) % 360
    return Track(
        seed=str(payload.get("name", map_path.stem)),
        polyline=polyline,
        total_length=total_length,
        start_position=start_position,
        start_angle=start_angle,
        cell_size=cell_size,
        half_width=half_width,
        canvas_size=(int(payload["canvas"]["width"]), int(payload["canvas"]["height"])),
        closed_loop=closed_loop,
    )


def load_track_ref(ref: MapRef, cell_size: int = 120, half_width: float = 34.0) -> Track:
    if isinstance(ref, int):
        return generate_track(seed=ref, cell_size=cell_size, half_width=half_width)
    return load_tile_track(ref, half_width=half_width)


@dataclass
class Cell:
    x: int
    y: int
    walls: dict[str, bool]

    def has_all_walls(self) -> bool:
        return all(self.walls.values())

    def knock_down_wall(self, other: "Cell", wall: str) -> None:
        wall_pairs = {"N": "S", "S": "N", "E": "W", "W": "E"}
        self.walls[wall] = False
        other.walls[wall_pairs[wall]] = False


class Maze:
    def __init__(self, nx: int, ny: int) -> None:
        self.nx = nx
        self.ny = ny
        self.cells = [
            [Cell(x=x, y=y, walls={"N": True, "S": True, "E": True, "W": True}) for y in range(ny)]
            for x in range(nx)
        ]

    def cell_at(self, x: int, y: int) -> Cell:
        return self.cells[x][y]

    def valid_neighbours(self, cell: Cell) -> list[tuple[str, Cell]]:
        delta = [("W", (-1, 0)), ("E", (1, 0)), ("S", (0, 1)), ("N", (0, -1))]
        neighbours: list[tuple[str, Cell]] = []
        for direction, (dx, dy) in delta:
            x2 = cell.x + dx
            y2 = cell.y + dy
            if 0 <= x2 < self.nx and 0 <= y2 < self.ny:
                neighbour = self.cell_at(x2, y2)
                if neighbour.has_all_walls():
                    neighbours.append((direction, neighbour))
        return neighbours


def generate_track(
    seed: int,
    cell_size: int = 120,
    half_width: float = 34.0,
    grid_width: int = 10,
    grid_height: int = 5,
) -> Track:
    rng = random.Random(seed)
    maze = Maze(grid_width, grid_height)
    start = maze.cell_at(0, 3)
    current = start
    ordered_cells = [(current.x, current.y)]
    track_length = 1

    while True:
        neighbours = maze.valid_neighbours(current)
        if neighbours:
            if current.x == 0 and current.y == 3:
                next_cell = maze.cell_at(0, 2)
                current.knock_down_wall(next_cell, "N")
                current = next_cell
                ordered_cells.append((current.x, current.y))
                track_length += 1
                continue

            direction, next_cell = rng.choice(neighbours)
            current.knock_down_wall(next_cell, direction)
            current = next_cell
            ordered_cells.append((current.x, current.y))
            track_length += 1
            continue

        if current.x == 0 and current.y == 4 and track_length > 40:
            break

        track_length = 1
        maze = Maze(grid_width, grid_height)
        for forced_x in range(3, 7):
            maze.cell_at(forced_x, 3).walls["N"] = False
        start = maze.cell_at(0, 3)
        current = start
        ordered_cells = [(current.x, current.y)]

    margin_x = 70
    margin_y = 85
    polyline: list[Point] = []
    for cell_x, cell_y in ordered_cells:
        polyline.append(
            (
                margin_x + (cell_x * cell_size) + (cell_size / 2),
                margin_y + (cell_y * cell_size) + (cell_size / 2),
            )
        )

    total_length = 0.0
    for start_point, end_point in zip(polyline[:-1], polyline[1:]):
        total_length += math.dist(start_point, end_point)

    start_position = polyline[0]
    next_position = polyline[1]
    dx = next_position[0] - start_position[0]
    dy = next_position[1] - start_position[1]
    start_angle = (-math.degrees(math.atan2(dx, dy))) % 360
    canvas_width = (grid_width * cell_size) + (margin_x * 2)
    canvas_height = (grid_height * cell_size) + (margin_y * 2)
    return Track(
        seed=seed,
        polyline=polyline,
        total_length=total_length,
        start_position=start_position,
        start_angle=start_angle,
        cell_size=cell_size,
        half_width=half_width,
        canvas_size=(canvas_width, canvas_height),
    )
