from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Iterable


GRID_COLUMNS = 10
GRID_ROWS = 5
BLOCK_SIZE = 146
MAP_OFFSET_X = 70
MAP_OFFSET_Y = 85
START_CELL = (0, 3)
END_CELL = (0, 4)
MIN_ROUTE_CELLS = 41

DIRECTION_DELTAS = {
    "N": (0, -1),
    "S": (0, 1),
    "E": (1, 0),
    "W": (-1, 0),
}
OPPOSITE_DIRECTION = {"N": "S", "S": "N", "E": "W", "W": "E"}

TILE_NAMES = {
    frozenset(("N", "S")): "Straight2",
    frozenset(("E", "W")): "Straight1",
    frozenset(("N", "W")): "Curve3",
    frozenset(("S", "W")): "Curve2",
    frozenset(("S", "E")): "Curve1",
    frozenset(("N", "E")): "Curve4",
}


@dataclass(frozen=True, slots=True)
class TrackLayout:
    seed: int
    route_cells: tuple[tuple[int, int], ...]

    def connections_for(self, index: int) -> frozenset[str]:
        current = self.route_cells[index]
        previous = self.route_cells[index - 1]
        following = self.route_cells[(index + 1) % len(self.route_cells)]
        return frozenset(
            (
                direction_between(current, previous),
                direction_between(current, following),
            )
        )

    def tile_name_for(self, index: int) -> str:
        connections = self.connections_for(index)
        try:
            return TILE_NAMES[connections]
        except KeyError as exc:
            raise ValueError(
                f"Unsupported track connections at {self.route_cells[index]}: "
                f"{sorted(connections)}"
            ) from exc

    @property
    def centerline(self) -> tuple[tuple[float, float], ...]:
        return tuple(cell_center(cell) for cell in self.route_cells)

    @property
    def spawn(self) -> dict[str, float]:
        start = self.centerline[0]
        following = self.centerline[1]
        return {
            "x": round(start[0], 2),
            "y": round(start[1], 2),
            "angle": round(angle_for_vector(following[0] - start[0], following[1] - start[1]), 2),
        }


def generate_track_layout(
    seed: int,
    *,
    min_route_cells: int = MIN_ROUTE_CELLS,
    max_attempts: int = 20_000,
) -> TrackLayout:
    rng = random.Random(seed)

    for _ in range(max_attempts):
        route = _generate_candidate_route(rng)
        if route[-1] != END_CELL or len(route) < min_route_cells:
            continue

        layout = TrackLayout(seed=seed, route_cells=tuple(route))
        validate_track_layout(layout, min_route_cells=min_route_cells)
        return layout

    raise RuntimeError(
        f"Unable to generate a valid track for seed {seed} "
        f"after {max_attempts} attempts"
    )


def validate_track_layout(
    layout: TrackLayout,
    *,
    min_route_cells: int = MIN_ROUTE_CELLS,
) -> None:
    route = layout.route_cells
    if len(route) < min_route_cells:
        raise ValueError(
            f"Track contains {len(route)} cells; expected at least {min_route_cells}"
        )
    if route[0] != START_CELL:
        raise ValueError(f"Track must start at {START_CELL}")
    if route[1] != (START_CELL[0], START_CELL[1] - 1):
        raise ValueError("Track must leave the start cell toward the north")
    if route[-1] != END_CELL:
        raise ValueError(f"Track must end at {END_CELL}")
    if len(set(route)) != len(route):
        raise ValueError("Track route contains repeated cells")

    for cell in route:
        if not _inside_grid(cell):
            raise ValueError(f"Track cell is outside the grid: {cell}")

    closed_route = route + (route[0],)
    for current, following in zip(closed_route, closed_route[1:]):
        direction_between(current, following)

    for index in range(len(route)):
        layout.tile_name_for(index)


def build_checkpoints(
    layout: TrackLayout,
    *,
    count: int = 18,
    half_gate_width: float = 50.0,
) -> list[dict]:
    if count <= 0:
        raise ValueError("Checkpoint count must be positive")

    points = layout.centerline
    closed_points = points + (points[0],)
    segments = [
        (
            start,
            end,
            math.hypot(end[0] - start[0], end[1] - start[1]),
        )
        for start, end in zip(closed_points, closed_points[1:])
    ]
    total_length = sum(length for _, _, length in segments)

    checkpoints = []
    for index in range(count):
        distance = total_length * (index + 1) / count
        center, tangent = _point_and_tangent_at_distance(segments, distance)
        normal = (-tangent[1], tangent[0])
        a = (
            center[0] + normal[0] * half_gate_width,
            center[1] + normal[1] * half_gate_width,
        )
        b = (
            center[0] - normal[0] * half_gate_width,
            center[1] - normal[1] * half_gate_width,
        )
        checkpoints.append(
            {
                "index": index,
                "center": [round(center[0], 2), round(center[1], 2)],
                "a": [round(a[0], 2), round(a[1], 2)],
                "b": [round(b[0], 2), round(b[1], 2)],
            }
        )
    return checkpoints


def cell_origin(cell: tuple[int, int]) -> tuple[int, int]:
    return (
        MAP_OFFSET_X + cell[0] * BLOCK_SIZE,
        MAP_OFFSET_Y + cell[1] * BLOCK_SIZE,
    )


def cell_center(cell: tuple[int, int]) -> tuple[float, float]:
    origin_x, origin_y = cell_origin(cell)
    half_block = BLOCK_SIZE / 2
    return origin_x + half_block, origin_y + half_block


def direction_between(
    start: tuple[int, int],
    end: tuple[int, int],
) -> str:
    delta = end[0] - start[0], end[1] - start[1]
    for direction, expected_delta in DIRECTION_DELTAS.items():
        if delta == expected_delta:
            return direction
    raise ValueError(f"Track cells are not adjacent: {start} -> {end}")


def angle_for_vector(dx: float, dy: float) -> float:
    return (-math.degrees(math.atan2(dx, dy))) % 360


def _generate_candidate_route(rng: random.Random) -> list[tuple[int, int]]:
    route = [START_CELL, (START_CELL[0], START_CELL[1] - 1)]
    visited = set(route)
    current = route[-1]

    while True:
        neighbours = [
            neighbour
            for neighbour in _neighbours(current)
            if neighbour not in visited
        ]
        if not neighbours:
            return route
        current = rng.choice(neighbours)
        route.append(current)
        visited.add(current)


def _neighbours(cell: tuple[int, int]) -> Iterable[tuple[int, int]]:
    x, y = cell
    for dx, dy in DIRECTION_DELTAS.values():
        neighbour = x + dx, y + dy
        if _inside_grid(neighbour):
            yield neighbour


def _inside_grid(cell: tuple[int, int]) -> bool:
    return 0 <= cell[0] < GRID_COLUMNS and 0 <= cell[1] < GRID_ROWS


def _point_and_tangent_at_distance(
    segments: list[
        tuple[
            tuple[float, float],
            tuple[float, float],
            float,
        ]
    ],
    distance: float,
) -> tuple[tuple[float, float], tuple[float, float]]:
    remaining = distance
    for start, end, length in segments:
        if remaining <= length:
            ratio = 0.0 if length == 0 else remaining / length
            center = (
                start[0] + (end[0] - start[0]) * ratio,
                start[1] + (end[1] - start[1]) * ratio,
            )
            tangent = (
                (end[0] - start[0]) / length,
                (end[1] - start[1]) / length,
            )
            return center, tangent
        remaining -= length

    start, end, length = segments[-1]
    return end, (
        (end[0] - start[0]) / length,
        (end[1] - start[1]) / length,
    )
