from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from game_engine.backend.car import Car, configure_car
from game_engine.backend.serialization import apply_weight_payload
from game_engine.backend.settings import (
    DEFAULT_TRACK_BACK_PATH,
    DEFAULT_TRACK_FRONT_PATH,
    FPS,
    MAX_SPEED,
    TRACK_BACK_PATH,
    TRACK_FRONT_PATH,
)
from server.models import EvaluationResult, TrackScore
from shared.contracts import EXPECTED_LAYER_SIZES, WeightPayload


@dataclass(frozen=True, slots=True)
class OfficialTrack:
    track_id: str
    name: str
    collision_path: Path
    render_path: Path
    spawn_x: float = 120.0
    spawn_y: float = 480.0
    spawn_angle: float = 180.0


OFFICIAL_TRACKS = [
    OfficialTrack(
        track_id="official-default",
        name="Official Default",
        collision_path=DEFAULT_TRACK_BACK_PATH,
        render_path=DEFAULT_TRACK_FRONT_PATH,
        spawn_x=120.0,
        spawn_y=480.0,
    ),
    OfficialTrack(
        track_id="official-generated",
        name="Official Generated",
        collision_path=TRACK_BACK_PATH,
        render_path=TRACK_FRONT_PATH,
        spawn_x=140.0,
        spawn_y=610.0,
    ),
    OfficialTrack(
        track_id="official-default-repeat",
        name="Official Default Reverse Check",
        collision_path=DEFAULT_TRACK_BACK_PATH,
        render_path=DEFAULT_TRACK_FRONT_PATH,
        spawn_x=120.0,
        spawn_y=480.0,
    ),
]


class OfficialEvaluator:
    def __init__(
        self,
        tracks: list[OfficialTrack] | None = None,
        seconds_per_track: int = 60,
        fps: int = FPS,
    ) -> None:
        self.tracks = tracks or OFFICIAL_TRACKS
        self.seconds_per_track = seconds_per_track
        self.fps = fps

    def evaluate(self, payload: WeightPayload) -> EvaluationResult:
        pygame.init()
        track_scores = [
            self.evaluate_track(payload, track)
            for track in self.tracks
        ]
        best_track = max(track_scores, key=lambda score: score.score, default=None)
        return EvaluationResult(
            official_score=sum(track_score.score for track_score in track_scores),
            track_scores=track_scores,
            best_track_id=best_track.track_id if best_track else None,
            best_track_score=best_track.score if best_track else 0.0,
        )

    def evaluate_track(
        self,
        payload: WeightPayload,
        track: OfficialTrack,
    ) -> TrackScore:
        collision_map = pygame.image.load(track.collision_path)
        configure_car(collision_map, None, MAX_SPEED)

        car = Car(list(EXPECTED_LAYER_SIZES))
        apply_weight_payload(car, payload)
        car.x = track.spawn_x
        car.y = track.spawn_y
        car.angle = track.spawn_angle
        car.velocity = 0
        car.acceleration = 0
        car.score = 0
        car.collided = False
        car.yaReste = False

        frames_simulated = 0
        collided = False
        max_frames = self.seconds_per_track * self.fps
        for frame in range(max_frames):
            try:
                car.update()
                if car.collision():
                    collided = True
                    break
                car.feedforward()
                car.takeAction()
            except (IndexError, pygame.error):
                collided = True
                break
            frames_simulated = frame + 1

        return TrackScore(
            track_id=track.track_id,
            track_name=track.name,
            score=float(car.score),
            frames_simulated=frames_simulated,
            collided=collided,
        )
