from __future__ import annotations

import base64
import json
import os
import socket
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen

import pygame

from game_engine.backend.assets import load_game_assets
from game_engine.backend.car import Car, configure_car
from game_engine.backend.serialization import apply_weight_payload
from game_engine.backend.settings import FPS, MAX_SPEED, PROJECT_ROOT, SCREEN_SIZE, WHITE
from shared.contracts import EXPECTED_LAYER_SIZES, SubmissionPayload


Color = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class ReplayTrack:
    map_id: str
    front_path: Path
    back_path: Path
    spawn_x: float
    spawn_y: float
    spawn_angle: float


@dataclass(slots=True)
class ReplayCar:
    item: dict[str, Any]
    car: Any
    color: Color
    crashed: bool = False

    @property
    def label(self) -> str:
        group_id = str(self.item.get("group_id", "?"))
        username = str(self.item.get("username", "unknown"))
        return f"G{group_id} {username}"

    @property
    def score_laps(self) -> float:
        return float(self.item.get("score_laps") or 0.0)


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


class ReplayFeed:
    def __init__(self, server_url: str, top_n: int) -> None:
        self.server_url = server_url
        self.top_n = top_n
        self.pending_state: dict[str, Any] | None = None
        self.status = "Waiting for replay data"
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._listen_ws, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1.0)

    def set_pending_state(self, state: dict[str, Any] | None, status: str) -> None:
        with self._lock:
            self.pending_state = state
            self.status = status

    def pop_pending_state(self) -> tuple[dict[str, Any] | None, str]:
        with self._lock:
            state = self.pending_state
            self.pending_state = None
            return state, self.status

    def _listen_ws(self) -> None:
        while not self._stop_event.is_set():
            try:
                for event in _websocket_events(self.server_url, self._stop_event):
                    replay_top = event.get("replay_top", [])
                    if replay_top:
                        self.set_pending_state(
                            {
                                "phase": event.get("phase", "unknown"),
                                "map": event.get("map"),
                                "items": replay_top[: self.top_n],
                            },
                            f"Live update: {len(replay_top[: self.top_n])} cars",
                        )
            except OSError as exc:
                self.set_pending_state(None, f"WS disconnected: {exc}")
                self._stop_event.wait(5.0)


REPLAY_COLORS: list[Color] = [
    (60, 145, 255),
    (255, 196, 70),
    (85, 220, 145),
    (255, 95, 115),
    (190, 130, 255),
    (120, 225, 230),
    (235, 135, 85),
    (210, 230, 95),
    (245, 135, 210),
    (170, 180, 190),
]
DIM_COLOR: Color = (95, 105, 115)


def run(server_url: str = "http://127.0.0.1:8000", top_n: int = 10) -> None:
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
    feed = ReplayFeed(server_url, top_n)
    feed.start()

    try:
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return

            now = time.monotonic()
            if session is None and now >= next_refresh_at:
                state, feed_status = feed.pop_pending_state()
                if state is None:
                    try:
                        state = fetch_replay_state(server_url, top_n)
                        feed_status = f"Connected: {len(state.get('items', []))} cars"
                    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
                        status = f"Disconnected: {exc}"
                        next_refresh_at = now + 5.0
                        state = None
                if state and state.get("items"):
                    session, background = load_replay_scene(state, assets, top_n)
                    status = feed_status
                elif state is not None:
                    status = "Waiting for evaluated submissions"
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
    finally:
        feed.stop()
        pygame.quit()


def fetch_replay_state(server_url: str, top_n: int) -> dict[str, Any]:
    url = server_url.rstrip("/") + f"/api/replay/top?n={top_n}"
    with urlopen(url, timeout=5.0) as response:
        return json.loads(response.read().decode("utf-8"))


def load_replay_scene(
    state: dict[str, Any],
    assets: Any,
    top_n: int = 10,
) -> tuple[ReplaySession, pygame.Surface]:
    track = replay_track_from_state(state)
    collision_map = pygame.image.load(track.back_path)
    configure_car(collision_map, assets.green_small_car, MAX_SPEED)

    replay_cars = [
        build_replay_car(
            item=item,
            color=REPLAY_COLORS[index % len(REPLAY_COLORS)],
            track=track,
            car_image=assets.green_small_car,
        )
        for index, item in enumerate(state.get("items", [])[:top_n])
    ]
    background = pygame.image.load(track.front_path)
    return ReplaySession(replay_cars, FPS * 30), background


def replay_track_from_state(state: dict[str, Any]) -> ReplayTrack:
    map_data = state["map"]
    spawn = map_data["spawn"]
    return ReplayTrack(
        map_id=str(map_data["map_id"]),
        front_path=_project_path(str(map_data["front_path"])),
        back_path=_project_path(str(map_data["back_path"])),
        spawn_x=float(spawn["x"]),
        spawn_y=float(spawn["y"]),
        spawn_angle=float(spawn.get("angle", 180.0)),
    )


def build_replay_car(
    *,
    item: dict[str, Any],
    color: Color,
    track: ReplayTrack,
    car_image: pygame.Surface | None,
) -> ReplayCar:
    car = Car(list(EXPECTED_LAYER_SIZES))
    payload = SubmissionPayload(
        group_id=str(item["group_id"]),
        username=str(item["username"]),
        weights=item["weights"],
        biases=item["biases"],
    )
    apply_weight_payload(car, payload)
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
        label = font.render(replay_car.label, True, color)
        screen.blit(label, (x + 10, y - 28))


def draw_overlay(
    screen: pygame.Surface,
    font: pygame.font.Font,
    small_font: pygame.font.Font,
    session: ReplaySession,
    status: str,
) -> None:
    title = font.render("Top 10 Replay", True, WHITE)
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
        line = f"#{index} {replay_car.label}  {replay_car.score_laps:.2f} laps  {state}"
        rendered = small_font.render(line, True, color)
        screen.blit(rendered, (24, y))
        y += rendered.get_height() + 8


def _project_path(path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return PROJECT_ROOT / candidate


def _websocket_events(server_url: str, stop_event: threading.Event):
    parsed = urlparse(server_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    with socket.create_connection((host, port), timeout=5.0) as sock:
        sock.settimeout(5.0)
        request = (
            "GET /ws/events HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        sock.sendall(request.encode("ascii"))
        response = sock.recv(4096)
        if b"101" not in response.split(b"\r\n", 1)[0]:
            raise OSError("websocket upgrade failed")
        while not stop_event.is_set():
            payload = _read_ws_text_frame(sock)
            if payload:
                yield json.loads(payload)


def _read_ws_text_frame(sock: socket.socket) -> str:
    header = _recv_exact(sock, 2)
    first, second = header[0], header[1]
    opcode = first & 0x0F
    length = second & 0x7F
    if length == 126:
        length = int.from_bytes(_recv_exact(sock, 2), "big")
    elif length == 127:
        length = int.from_bytes(_recv_exact(sock, 8), "big")
    payload = _recv_exact(sock, length)
    if opcode == 8:
        raise OSError("websocket closed")
    if opcode != 1:
        return ""
    return payload.decode("utf-8")


def _recv_exact(sock: socket.socket, length: int) -> bytes:
    chunks = []
    remaining = length
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise OSError("socket closed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)
