from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from game_engine.backend.track import TrackGeometry


@dataclass(frozen=True, slots=True)
class FrameTelemetry:
    velocity: float
    progress_delta: float
    progress_ratio: float
    center_offset: float
    track_half_width: float
    heading_delta: float
    heading_alignment: float
    min_clearance: float
    is_stalled: bool
    is_spinning: bool
    is_wrong_way: bool
    time_elapsed: float
    collided: bool
    finished_now: bool


@dataclass(slots=True)
class EpisodeState:
    last_progress: float
    previous_angle: float
    cumulative_progress: float = 0.0
    training_fitness: float = 0.0
    frame: int = 0
    finished: bool = False


@dataclass(frozen=True, slots=True)
class StepResult:
    telemetry: FrameTelemetry
    step_fitness: float
    training_fitness: float


class Simulator:
    def __init__(self, track: TrackGeometry, fps: int) -> None:
        if fps <= 0:
            raise ValueError("fps must be positive")
        self.track = track
        self.fps = fps
        self._states: dict[int, EpisodeState] = {}

    def reset_car(self, car: Any) -> EpisodeState:
        car.refresh_track_state(self.track)
        projection = self.track.project(car.center)
        state = EpisodeState(
            last_progress=projection.progress,
            previous_angle=float(car.angle),
        )
        self._states[id(car)] = state
        car.fitness_score = 0.0
        return state

    def reset_population(self, population: Iterable[Any]) -> None:
        self._states.clear()
        for car in population:
            self.reset_car(car)

    def state_for(self, car: Any) -> EpisodeState:
        state = self._states.get(id(car))
        if state is None:
            state = self.reset_car(car)
        return state

    def step(
        self,
        car: Any,
        score_frame: Callable[[FrameTelemetry], float],
    ) -> StepResult:
        state = self.state_for(car)
        if bool(car.collided):
            raise ValueError("Cannot step a collided car")

        previous_angle = float(car.angle)
        car.feedforward()
        car.takeAction()
        car.update(self.track)

        projection = self.track.project(car.center)
        raw_progress_delta = projection.progress - state.last_progress
        half_track_length = self.track.total_length / 2.0
        if raw_progress_delta < -half_track_length:
            raw_progress_delta = (
                self.track.total_length - state.last_progress
            ) + projection.progress
        elif raw_progress_delta > half_track_length:
            raw_progress_delta -= self.track.total_length

        progress_delta = max(0.0, raw_progress_delta)
        state.cumulative_progress += progress_delta
        progress_ratio = min(
            1.0,
            max(0.0, state.cumulative_progress / self.track.total_length),
        )

        heading_delta = (
            (float(car.angle) - projection.target_heading + 180.0) % 360.0
        ) - 180.0
        heading_alignment = math.cos(math.radians(heading_delta))
        collided = bool(car.collision(self.track))
        finished_now = not state.finished and (
            state.cumulative_progress >= self.track.total_length
        )
        if finished_now:
            state.finished = True

        state.frame += 1
        telemetry = FrameTelemetry(
            velocity=float(car.velocity),
            progress_delta=progress_delta,
            progress_ratio=progress_ratio,
            center_offset=projection.center_offset,
            track_half_width=self.track.half_width,
            heading_delta=heading_delta,
            heading_alignment=heading_alignment,
            min_clearance=min(
                float(car.d1),
                float(car.d2),
                float(car.d3),
                float(car.d4),
                float(car.d5),
            ),
            is_stalled=float(car.velocity) < 0.5,
            is_spinning=(
                abs(float(car.angle) - previous_angle) >= 5.0
                and progress_delta < 0.1
            ),
            is_wrong_way=heading_alignment < 0.0,
            time_elapsed=state.frame / self.fps,
            collided=collided,
            finished_now=finished_now,
        )
        step_fitness = float(score_frame(telemetry))
        state.training_fitness += step_fitness
        state.last_progress = projection.progress
        state.previous_angle = float(car.angle)
        car.fitness_score = state.training_fitness
        car.collided = collided
        return StepResult(
            telemetry=telemetry,
            step_fitness=step_fitness,
            training_fitness=state.training_fitness,
        )
