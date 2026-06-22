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
        return _segments_intersect(previous, current, checkpoint.a, checkpoint.b) or (
            _distance(current, checkpoint.center) <= 52.0
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
                tracker.advance(previous, current)
                previous = current
                if car.collision():
                    collided = True
                    frames_simulated = frame + 1
                    break
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


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _segments_intersect(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
) -> bool:
    def orientation(
        p: tuple[float, float],
        q: tuple[float, float],
        r: tuple[float, float],
    ) -> float:
        return (q[1] - p[1]) * (r[0] - q[0]) - (q[0] - p[0]) * (r[1] - q[1])

    o1 = orientation(a, b, c)
    o2 = orientation(a, b, d)
    o3 = orientation(c, d, a)
    o4 = orientation(c, d, b)
    return (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0)
