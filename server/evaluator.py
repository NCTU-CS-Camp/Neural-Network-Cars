from __future__ import annotations

import math
import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from game_engine.backend.car import Car, configure_car
from game_engine.backend.serialization import apply_weight_payload
from game_engine.backend.settings import FPS, MAX_SPEED, PROJECT_ROOT
from server.models import CheckpointGate, EvaluationResult, OfficialMap
from server.official_maps import load_official_map
from shared.contracts import EXPECTED_LAYER_SIZES, SubmissionPayload


CHECKPOINT_CROSSING_TOLERANCE = 2.0


class CheckpointTracker:
    def __init__(self, checkpoints: list[CheckpointGate]) -> None:
        if not checkpoints:
            raise ValueError("official map must contain at least one checkpoint")
        self.checkpoints = checkpoints
        self.next_index = 0
        self.completed_laps = 0
        self.completed_total = 0

    def advance(self, previous: tuple[float, float], current: tuple[float, float]) -> None:
        for _ in range(len(self.checkpoints)):
            checkpoint = self.checkpoints[self.next_index]
            if not self._passed_checkpoint(previous, current, checkpoint):
                break
            self.completed_total += 1
            self.next_index += 1
            if self.next_index >= len(self.checkpoints):
                self.next_index = 0
                self.completed_laps += 1

    @property
    def score_laps(self) -> float:
        return self.completed_laps + (self.next_index / len(self.checkpoints))

    def _passed_checkpoint(
        self,
        previous: tuple[float, float],
        current: tuple[float, float],
        checkpoint: CheckpointGate,
    ) -> bool:
        return _segments_intersect(
            previous,
            current,
            checkpoint.a,
            checkpoint.b,
            tolerance=CHECKPOINT_CROSSING_TOLERANCE,
        )


class OfficialEvaluator:
    def __init__(
        self,
        *,
        seconds_per_run: int = 30,
        fps: int = FPS,
    ) -> None:
        self.seconds_per_run = seconds_per_run
        self.fps = fps

    def evaluate(
        self,
        payload: SubmissionPayload,
        official_map: OfficialMap | str,
    ) -> EvaluationResult:
        pygame.init()
        track = (
            load_official_map(official_map)
            if isinstance(official_map, str)
            else official_map
        )
        collision_map = pygame.image.load(_project_path(track.back_path))
        configure_car(collision_map, None, MAX_SPEED)

        car = Car(list(EXPECTED_LAYER_SIZES))
        apply_weight_payload(car, payload)
        car.reset_state(
            x=track.spawn_x,
            y=track.spawn_y,
            angle=track.spawn_angle,
            car_image=None,
        )

        tracker = CheckpointTracker(track.checkpoints)
        frames_simulated = 0
        collided = False
        previous = (float(car.x), float(car.y))
        max_frames = self.seconds_per_run * self.fps

        for frame in range(max_frames):
            try:
                car.update()
                current = (float(car.x), float(car.y))
                if car.collision():
                    collided = True
                    frames_simulated = frame + 1
                    break
                tracker.advance(previous, current)
                previous = current
                car.feedforward()
                car.takeAction()
            except (IndexError, pygame.error, ValueError):
                collided = True
                frames_simulated = frame + 1
                break
            frames_simulated = frame + 1

        return EvaluationResult(
            score_laps=float(tracker.score_laps),
            frames_simulated=frames_simulated,
            collided=collided,
            checkpoints_completed=tracker.completed_total,
            completed_laps=tracker.completed_laps,
            map_id=track.map_id,
        )


def _project_path(path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return PROJECT_ROOT / candidate


def _segments_intersect(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
    *,
    tolerance: float = 0.0,
) -> bool:
    if _segments_cross(a, b, c, d):
        return True
    return _segment_distance(a, b, c, d) <= tolerance


def _segments_cross(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
    *,
    epsilon: float = 1e-9,
) -> bool:
    o1 = _orientation(a, b, c)
    o2 = _orientation(a, b, d)
    o3 = _orientation(c, d, a)
    o4 = _orientation(c, d, b)

    if abs(o1) <= epsilon and _on_segment(a, c, b, epsilon=epsilon):
        return True
    if abs(o2) <= epsilon and _on_segment(a, d, b, epsilon=epsilon):
        return True
    if abs(o3) <= epsilon and _on_segment(c, a, d, epsilon=epsilon):
        return True
    if abs(o4) <= epsilon and _on_segment(c, b, d, epsilon=epsilon):
        return True

    return (o1 > epsilon) != (o2 > epsilon) and (o3 > epsilon) != (o4 > epsilon)


def _orientation(
    p: tuple[float, float],
    q: tuple[float, float],
    r: tuple[float, float],
) -> float:
    return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])


def _on_segment(
    p: tuple[float, float],
    q: tuple[float, float],
    r: tuple[float, float],
    *,
    epsilon: float,
) -> bool:
    return (
        min(p[0], r[0]) - epsilon <= q[0] <= max(p[0], r[0]) + epsilon
        and min(p[1], r[1]) - epsilon <= q[1] <= max(p[1], r[1]) + epsilon
    )


def _segment_distance(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
) -> float:
    return min(
        _point_segment_distance(a, c, d),
        _point_segment_distance(b, c, d),
        _point_segment_distance(c, a, b),
        _point_segment_distance(d, a, b),
    )


def _point_segment_distance(
    p: tuple[float, float],
    a: tuple[float, float],
    b: tuple[float, float],
) -> float:
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    length_squared = dx * dx + dy * dy
    if length_squared == 0:
        return math.hypot(p[0] - a[0], p[1] - a[1])

    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length_squared
    t = max(0.0, min(1.0, t))
    closest = (a[0] + t * dx, a[1] + t * dy)
    return math.hypot(p[0] - closest[0], p[1] - closest[1])
