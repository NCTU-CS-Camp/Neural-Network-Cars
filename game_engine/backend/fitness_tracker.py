from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from GA.fitness import FitnessStrategy, StepContext
from game_engine.backend.settings import SIMULATION_MAX_FRAMES
from game_engine.backend.track_geometry import TrackGeometry


def _angle_delta(angle_a: float, angle_b: float) -> float:
    return ((angle_a - angle_b + 180.0) % 360.0) - 180.0


@dataclass(slots=True)
class FitnessTracker:
    track: TrackGeometry
    strategy: FitnessStrategy
    fps: int
    max_frames: int = SIMULATION_MAX_FRAMES
    previous_progress: float = 0.0
    total_fitness: float = 0.0
    frame: int = 0
    finished: bool = False
    crashed: bool = False
    timed_out: bool = False
    last_context: StepContext | None = None

    @property
    def stopped(self) -> bool:
        return self.finished or self.crashed or self.timed_out

    @classmethod
    def for_car(
        cls,
        car: Any,
        *,
        track: TrackGeometry,
        strategy: FitnessStrategy,
        fps: int,
        max_frames: int = SIMULATION_MAX_FRAMES,
    ) -> "FitnessTracker":
        progress, _ = track.project((float(car.x), float(car.y)))
        car.fitness_score = 0.0
        car.finished = False
        car.timed_out = False
        return cls(
            track=track,
            strategy=strategy,
            fps=fps,
            max_frames=max_frames,
            previous_progress=progress,
        )

    def advance(
        self,
        car: Any,
        *,
        previous_angle: float,
        collided: bool,
    ) -> StepContext:
        if self.stopped:
            if self.last_context is None:
                raise RuntimeError("Stopped fitness tracker has no context")
            return self.last_context

        self.frame += 1
        progress, center_offset = self.track.project(
            (float(car.x), float(car.y))
        )
        raw_progress_delta = progress - self.previous_progress
        progress_delta = max(0.0, raw_progress_delta)
        reverse_progress_delta = max(0.0, -raw_progress_delta)
        progress_ratio = (
            progress / self.track.total_length
            if self.track.total_length
            else 0.0
        )
        target_heading = self.track.heading_at_progress(progress)
        heading_delta = _angle_delta(float(car.angle), target_heading)
        heading_alignment = math.cos(math.radians(heading_delta))
        distances = [
            float(getattr(car, name, 0.0))
            for name in ("d1", "d2", "d3", "d4", "d5")
        ]
        turn_amount = abs(_angle_delta(float(car.angle), previous_angle))
        finished_now = progress >= self.track.total_length
        context = StepContext(
            velocity=float(car.velocity),
            progress_delta=progress_delta,
            reverse_progress_delta=reverse_progress_delta,
            progress_ratio=progress_ratio,
            center_offset=center_offset,
            normalized_center_offset=center_offset / self.track.half_width,
            heading_alignment=heading_alignment,
            front_clearance=distances[0],
            min_clearance=min(distances),
            side_clearance_balance=abs(distances[3] - distances[4]),
            turn_amount=turn_amount,
            collided=collided,
            finished=finished_now,
            is_stalled=float(car.velocity) < 0.5,
            is_spinning=turn_amount >= 5.0 and progress_delta < 0.1,
            frame=self.frame,
            time_elapsed=self.frame / self.fps,
        )
        self.total_fitness += self.strategy.score_step(context)
        self.previous_progress = progress
        self.finished = finished_now
        self.crashed = collided
        self.timed_out = (
            self.frame >= self.max_frames and not finished_now and not collided
        )
        self.last_context = context

        car.fitness_score = self.total_fitness
        car.progress = progress
        car.progress_ratio = progress_ratio
        car.center_offset = center_offset
        car.finished = finished_now
        car.timed_out = self.timed_out
        return context
