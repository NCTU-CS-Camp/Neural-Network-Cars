from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

import pygame

from game_engine.backend.assets import load_game_assets
from game_engine.backend.car import Car, configure_car
from game_engine.backend.serialization import apply_weight_payload
from game_engine.backend.settings import (
    DEFAULT_TRACK_BACK_PATH,
    DEFAULT_TRACK_FRONT_PATH,
    FPS,
    MAX_SPEED,
    SCREEN_SIZE,
    TRACK_BACK_PATH,
    TRACK_FRONT_PATH,
    WHITE,
)
from shared.contracts import EXPECTED_LAYER_SIZES, WeightPayload


Color = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class ReplayTrack:
    track_id: str
    front_path: Path
    back_path: Path
    spawn_x: float
    spawn_y: float
    spawn_angle: float = 180.0


@dataclass(slots=True)
class ReplayCar:
    item: dict[str, Any]
    car: Any
    color: Color
    crashed: bool = False

    @property
    def nickname(self) -> str:
        return str(self.item.get("nickname", "unknown"))

    @property
    def official_score(self) -> float:
        return float(self.item.get("official_score") or 0.0)


@dataclass(slots=True)
class ReplaySession:
    cars: list[ReplayCar]
    frame_limit: int
    crash_hold_frames: int = FPS * 2
    frames: int = 0
    all_crashed_at_frame: int | None = None

    def tick(self) -> bool:
        update_replay_cars(self.cars)
        self.frames += 1
        if self.cars and all(replay_car.crashed for replay_car in self.cars):
            if self.all_crashed_at_frame is None:
                self.all_crashed_at_frame = self.frames
            held_frames = self.frames - self.all_crashed_at_frame
            return held_frames >= self.crash_hold_frames
        return self.frames >= self.frame_limit


REPLAY_TRACKS = {
    "official-default": ReplayTrack(
        "official-default",
        DEFAULT_TRACK_FRONT_PATH,
        DEFAULT_TRACK_BACK_PATH,
        120.0,
        480.0,
    ),
    "official-generated": ReplayTrack(
        "official-generated",
        TRACK_FRONT_PATH,
        TRACK_BACK_PATH,
        140.0,
        610.0,
    ),
    "official-default-repeat": ReplayTrack(
        "official-default-repeat",
        DEFAULT_TRACK_FRONT_PATH,
        DEFAULT_TRACK_BACK_PATH,
        120.0,
        480.0,
    ),
}
SIMULTANEOUS_TRACK_ID = "official-default"
REPLAY_COLORS: list[Color] = [
    (60, 145, 255),
    (255, 196, 70),
    (85, 220, 145),
    (255, 95, 115),
    (190, 130, 255),
]
DIM_COLOR: Color = (95, 105, 115)


def run(server_url: str = "http://127.0.0.1:8000", top_n: int = 5) -> None:
    pygame.init()
    screen = pygame.display.set_mode(SCREEN_SIZE)
    pygame.display.set_caption("Neural Cars Replay")
    clock = pygame.time.Clock()
    font = pygame.font.Font("freesansbold.ttf", 24)
    small_font = pygame.font.Font("freesansbold.ttf", 18)
    assets = load_game_assets()

    session: ReplaySession | None = None
    background: pygame.Surface | None = None
    status = "Waiting for replay data"
    next_refresh_at = 0.0

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return

        now = time.monotonic()
        if now >= next_refresh_at:
            try:
                items = fetch_replay_items(server_url, top_n)
                if items:
                    session, background = load_replay_scene(items, assets, top_n)
                    status = f"Connected: {len(session.cars)} cars"
                    next_refresh_at = now + 60.0
                else:
                    session = None
                    background = None
                    status = "Waiting for evaluated submissions"
                    next_refresh_at = now + 5.0
            except (URLError, TimeoutError, json.JSONDecodeError) as exc:
                session = None
                background = None
                status = f"Disconnected: {exc}"
                next_refresh_at = now + 5.0

        screen.fill((0, 0, 0))
        if session and background:
            screen.blit(background, (0, 0))
            round_finished = session.tick()
            draw_replay_cars(screen, small_font, session.cars)
            draw_overlay(screen, font, small_font, session, status)
            if round_finished:
                session = None
                next_refresh_at = 0.0
        else:
            text = font.render(status, True, WHITE)
            screen.blit(text, (32, 32))

        pygame.display.update()
        clock.tick(FPS)


def fetch_replay_items(server_url: str, top_n: int) -> list[dict[str, Any]]:
    url = server_url.rstrip("/") + f"/api/replay/top?n={top_n}"
    with urlopen(url, timeout=5.0) as response:
        data = json.loads(response.read().decode("utf-8"))
    return list(data.get("items", []))


def load_replay_scene(
    items: list[dict[str, Any]],
    assets: Any,
    top_n: int = 5,
) -> tuple[ReplaySession, pygame.Surface]:
    track = REPLAY_TRACKS[SIMULTANEOUS_TRACK_ID]
    collision_map = pygame.image.load(track.back_path)
    configure_car(collision_map, assets.green_small_car, MAX_SPEED)

    replay_cars = [
        build_replay_car(
            item=item,
            color=REPLAY_COLORS[index % len(REPLAY_COLORS)],
            track=track,
            car_image=assets.green_small_car,
        )
        for index, item in enumerate(items[:top_n])
    ]
    background = pygame.image.load(track.front_path)
    return ReplaySession(replay_cars, FPS * 60), background


def build_replay_car(
    *,
    item: dict[str, Any],
    color: Color,
    track: ReplayTrack,
    car_image: pygame.Surface | None,
) -> ReplayCar:
    car = Car(list(EXPECTED_LAYER_SIZES))
    apply_weight_payload(car, WeightPayload.from_dict(item["payload"]))
    car.reset_state(
        track.spawn_x,
        track.spawn_y,
        angle=track.spawn_angle,
        car_image=car_image,
    )
    return ReplayCar(item=item, car=car, color=color)


def update_replay_cars(replay_cars: list[ReplayCar]) -> None:
    for replay_car in replay_cars:
        step_replay_car(replay_car)


def step_replay_car(replay_car: ReplayCar) -> None:
    if replay_car.crashed:
        return

    car = replay_car.car
    try:
        car.update()
        if car.collision():
            car.collided = True
            replay_car.crashed = True
            return
        car.feedforward()
        car.takeAction()
    except (IndexError, pygame.error):
        car.collided = True
        replay_car.crashed = True


def draw_replay_cars(
    screen: pygame.Surface,
    font: pygame.font.Font,
    replay_cars: list[ReplayCar],
) -> None:
    for replay_car in replay_cars:
        color = DIM_COLOR if replay_car.crashed else replay_car.color
        replay_car.car.draw(screen)
        x = int(replay_car.car.x)
        y = int(replay_car.car.y)
        pygame.draw.circle(screen, color, (x, y), 7)
        label = font.render(replay_car.nickname, True, color)
        screen.blit(label, (x + 10, y - 28))


def draw_overlay(
    screen: pygame.Surface,
    font: pygame.font.Font,
    small_font: pygame.font.Font,
    session: ReplaySession,
    status: str,
) -> None:
    title = font.render("Top 5 Simultaneous Replay", True, WHITE)
    screen.blit(title, (24, 24))
    subtitle = small_font.render(
        f"{status}  |  Frame {session.frames}/{session.frame_limit}",
        True,
        (210, 218, 226),
    )
    screen.blit(subtitle, (24, 56))

    y = 92
    for index, replay_car in enumerate(session.cars, start=1):
        color = DIM_COLOR if replay_car.crashed else replay_car.color
        state = "crashed" if replay_car.crashed else "running"
        line = (
            f"#{index} {replay_car.nickname}  "
            f"{replay_car.official_score:.1f}  {state}"
        )
        rendered = small_font.render(line, True, color)
        screen.blit(rendered, (24, y))
        y += rendered.get_height() + 8
