from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pygame

from game_engine.backend.assets import load_game_assets
from game_engine.backend.car import Car, configure_car
from game_engine.backend.serialization import apply_weight_payload
from game_engine.backend.settings import (
    FPS,
    MAX_SPEED,
    SCREEN_SIZE,
    TRACK_BACK_PATH,
    TRACK_FRONT_PATH,
    WHITE,
    DEFAULT_TRACK_BACK_PATH,
    DEFAULT_TRACK_FRONT_PATH,
)
from shared.contracts import EXPECTED_LAYER_SIZES, WeightPayload


@dataclass(frozen=True, slots=True)
class ReplayTrack:
    track_id: str
    front_path: Path
    back_path: Path
    spawn_x: float
    spawn_y: float
    spawn_angle: float = 180.0


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


def run(server_url: str = "http://127.0.0.1:8000", top_n: int = 5) -> None:
    pygame.init()
    screen = pygame.display.set_mode(SCREEN_SIZE)
    pygame.display.set_caption("Neural Cars Replay")
    clock = pygame.time.Clock()
    font = pygame.font.Font("freesansbold.ttf", 24)
    small_font = pygame.font.Font("freesansbold.ttf", 18)
    assets = load_game_assets()

    items: list[dict] = []
    item_index = 0
    car: Car | None = None
    background: pygame.Surface | None = None
    status = "Waiting for replay data"
    next_refresh_at = 0.0
    frames = 0

    def load_item(item: dict) -> tuple[Car, pygame.Surface]:
        track_id = str(item.get("best_track_id") or "official-default")
        track = REPLAY_TRACKS.get(track_id) or REPLAY_TRACKS["official-default"]
        collision_map = pygame.image.load(track.back_path)
        configure_car(collision_map, assets.green_small_car, MAX_SPEED)
        loaded_car = Car(list(EXPECTED_LAYER_SIZES))
        apply_weight_payload(loaded_car, WeightPayload.from_dict(item["payload"]))
        loaded_car.x = track.spawn_x
        loaded_car.y = track.spawn_y
        loaded_car.angle = track.spawn_angle
        loaded_car.velocity = 0
        loaded_car.acceleration = 0
        loaded_car.score = 0
        loaded_car.collided = False
        return loaded_car, pygame.image.load(track.front_path)

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return

        now = time.monotonic()
        if now >= next_refresh_at:
            next_refresh_at = now + 5.0
            try:
                items = fetch_replay_items(server_url, top_n)
                if items:
                    item_index %= len(items)
                    car, background = load_item(items[item_index])
                    frames = 0
                    status = "Connected"
                else:
                    car = None
                    background = None
                    status = "Waiting for evaluated submissions"
            except (URLError, TimeoutError, json.JSONDecodeError) as exc:
                status = f"Disconnected: {exc}"

        screen.fill((0, 0, 0))
        if car and background and items:
            item = items[item_index]
            screen.blit(background, (0, 0))
            try:
                if not car.collided:
                    car.update()
                    if car.collision():
                        car.collided = True
                    else:
                        car.feedforward()
                        car.takeAction()
                car.draw(screen)
            except (IndexError, pygame.error):
                car.collided = True

            frames += 1
            if car.collided or frames >= FPS * 60:
                item_index = (item_index + 1) % len(items)
                car, background = load_item(items[item_index])
                frames = 0

            draw_overlay(screen, font, small_font, item, status)
        else:
            text = font.render(status, True, WHITE)
            screen.blit(text, (32, 32))

        pygame.display.update()
        clock.tick(FPS)


def fetch_replay_items(server_url: str, top_n: int) -> list[dict]:
    url = server_url.rstrip("/") + f"/api/replay/top?n={top_n}"
    with urlopen(url, timeout=5.0) as response:
        data = json.loads(response.read().decode("utf-8"))
    return list(data.get("items", []))


def draw_overlay(
    screen: pygame.Surface,
    font: pygame.font.Font,
    small_font: pygame.font.Font,
    item: dict,
    status: str,
) -> None:
    nickname = item.get("nickname", "unknown")
    score = item.get("official_score") or 0.0
    best_track_score = item.get("best_track_score") or 0.0
    lines = [
        f"{nickname}",
        f"Total: {score:.1f}",
        f"Best track: {best_track_score:.1f}",
        status,
    ]
    y = 24
    for index, line in enumerate(lines):
        rendered = (font if index == 0 else small_font).render(line, True, WHITE)
        screen.blit(rendered, (24, y))
        y += rendered.get_height() + 8
