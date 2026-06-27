from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pygame

from game_engine.backend.assets import GameAssets, load_game_assets
from game_engine.backend.car import Car
from game_engine.backend.serialization import apply_weight_payload
from game_engine.backend.settings import FPS, SCREEN_SIZE
from server.competition_config import (
    FRAME_LIMIT,
    PHASE_ONE_REPLAY_LIMIT,
    STAGNATION_TICKS,
)
from server.competition_maps import CompetitionMap, get_competition_map
from server.models import CompetitionId
from shared.contracts import EXPECTED_LAYER_SIZES, SubmissionPayload


Color = tuple[int, int, int]
BACKGROUND: Color = (11, 17, 24)
PANEL: Color = (16, 25, 33)
BORDER: Color = (39, 54, 67)
TEXT: Color = (244, 247, 251)
MUTED: Color = (157, 174, 191)
EASY_ACCENT: Color = (87, 211, 207)
HARD_ACCENT: Color = (244, 177, 111)
FINAL_ACCENT: Color = (217, 168, 255)
DIM_COLOR: Color = (92, 105, 116)
REPLAY_PROGRESS_DISTANCE_PX = 24.0
REPLAY_COLORS: list[Color] = [
    (76, 169, 255),
    (255, 105, 124),
    (250, 205, 86),
    (114, 224, 152),
    (188, 132, 255),
    (100, 221, 225),
    (255, 148, 93),
    (198, 227, 108),
    (244, 137, 199),
    (185, 196, 210),
    (121, 166, 255),
    (240, 173, 108),
    (112, 213, 191),
    (222, 143, 166),
    (173, 150, 240),
]


@dataclass(frozen=True, slots=True)
class ReplayTrack:
    competition_map: CompetitionMap
    front: pygame.Surface
    collision: pygame.Surface

    @property
    def spawn(self) -> dict[str, float]:
        return self.competition_map.spawn


@dataclass(slots=True)
class ReplayCar:
    item: dict[str, Any]
    car: Car
    color: Color
    crashed: bool = False
    stalled: bool = False
    stagnation_ticks: int = 0
    last_progress_position: tuple[float, float] | None = None

    def __post_init__(self) -> None:
        self.last_progress_position = (float(self.car.x), float(self.car.y))

    @property
    def label(self) -> str:
        state = " STALLED" if self.stalled else ""
        return f"#{self.item.get('rank', '?')} {self.item.get('username', 'unknown')}{state}"

    def observe_position(self) -> None:
        current = (float(self.car.x), float(self.car.y))
        previous = self.last_progress_position
        if previous is None:
            self.last_progress_position = current
            return
        if math.dist(previous, current) >= REPLAY_PROGRESS_DISTANCE_PX:
            self.last_progress_position = current
            self.stagnation_ticks = 0
            return
        self.stagnation_ticks += 1
        if self.stagnation_ticks >= STAGNATION_TICKS:
            self.stalled = True


@dataclass(slots=True)
class ReplaySession:
    competition_id: str
    track: ReplayTrack
    cars: list[ReplayCar]
    leaderboard: list[dict[str, Any]]
    frame_limit: int = FRAME_LIMIT
    frames: int = 0
    all_crashed_at_frame: int | None = None

    def tick(self) -> bool:
        update_replay_cars(self.cars)
        self.frames += 1
        if self.cars and all(replay_car.crashed or replay_car.stalled for replay_car in self.cars):
            if self.all_crashed_at_frame is None:
                self.all_crashed_at_frame = self.frames
            return self.frames - self.all_crashed_at_frame >= FPS * 2
        return self.frames >= self.frame_limit


def run(
    server_url: str | None = None,
    token: str | None = None,
) -> None:
    pygame.init()
    screen = pygame.display.set_mode(SCREEN_SIZE)
    pygame.display.set_caption("Neural Cars Competition Replay")
    clock = pygame.time.Clock()
    fonts = _fonts()
    assets = load_game_assets()
    replay_token = token or os.environ.get("COMPETITION_REPLAY_TOKEN", "admin")
    replay_url = server_url or os.environ.get(
        "COMPETITION_SERVER_URL", "http://127.0.0.1:8000"
    )

    state: dict[str, Any] | None = None
    sessions: dict[str, ReplaySession] = {}
    next_fetch_at = 0.0
    next_generation_check_at = 0.0
    replay_generation: int | None = None
    status = "Connecting to protected replay feed"

    try:
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return

            now = time.monotonic()
            if not sessions and now >= next_fetch_at:
                try:
                    state = fetch_replay_state(replay_url, replay_token)
                    sessions = load_replay_sessions(state, assets)
                    replay_generation = int(state.get("replay_generation", 0))
                    status = "LIVE REPLAY"
                except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
                    status = f"Replay feed unavailable: {exc}"
                    next_fetch_at = now + 5.0

            if sessions and now >= next_generation_check_at:
                try:
                    current_generation = fetch_replay_generation(replay_url)
                    if replay_generation is not None and current_generation != replay_generation:
                        sessions = {}
                        state = None
                        next_fetch_at = 0.0
                        status = "Restarting replay"
                    next_generation_check_at = now + 1.0
                except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError):
                    next_generation_check_at = now + 5.0

            screen.fill(BACKGROUND)
            if state is None:
                _draw_centered(screen, fonts["title"], status, SCREEN_SIZE[1] // 2)
            elif state.get("stage") == "final":
                session = sessions.get("final")
                if session is not None:
                    finished = _draw_final(screen, session, fonts, status)
                    if finished:
                        sessions = {}
                        next_fetch_at = 0.0
                else:
                    _draw_final_waiting(screen, fonts, status)
                    next_fetch_at = now + 3.0
            else:
                easy = sessions.get("easy")
                hard = sessions.get("hard")
                if easy is not None and hard is not None:
                    finished = _draw_phase_one(screen, easy, hard, fonts, status)
                    if finished:
                        sessions = {}
                        next_fetch_at = 0.0
                else:
                    _draw_phase_one_waiting(screen, fonts, status)
                    next_fetch_at = now + 3.0

            pygame.display.flip()
            clock.tick(FPS)
    finally:
        pygame.quit()


def fetch_replay_state(server_url: str, token: str) -> dict[str, Any]:
    request = Request(
        server_url.rstrip("/") + "/v2/admin/replay",
        headers={"X-Admin-Token": token},
        method="GET",
    )
    with urlopen(request, timeout=5.0) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_replay_generation(server_url: str) -> int:
    with urlopen(server_url.rstrip("/") + "/v2/state", timeout=5.0) as response:
        state = json.loads(response.read().decode("utf-8"))
    return int(state["replay_generation"])


def load_replay_sessions(state: dict[str, Any], assets: GameAssets) -> dict[str, ReplaySession]:
    sessions = {}
    for competition_id, replay in state.get("replays", {}).items():
        sessions[competition_id] = load_replay_session(
            competition_id,
            replay,
            assets,
        )
    return sessions


def load_replay_session(
    competition_id: str,
    replay: dict[str, Any],
    assets: GameAssets,
) -> ReplaySession:
    identifier = CompetitionId(competition_id)
    competition_map = get_competition_map(identifier)
    track = ReplayTrack(
        competition_map=competition_map,
        front=pygame.image.load(competition_map.front_path),
        collision=competition_map.build_collision_surface(),
    )
    cars = [
        build_replay_car(
            item=item,
            color=REPLAY_COLORS[index % len(REPLAY_COLORS)],
            track=track,
            car_image=assets.green_small_car,
        )
        for index, item in enumerate(replay.get("items", [])[:PHASE_ONE_REPLAY_LIMIT])
    ]
    return ReplaySession(
        competition_id=competition_id,
        track=track,
        cars=cars,
        leaderboard=list(replay.get("leaderboard", [])),
    )


def build_replay_car(
    *,
    item: dict[str, Any],
    color: Color,
    track: ReplayTrack,
    car_image: pygame.Surface,
) -> ReplayCar:
    car = Car(list(EXPECTED_LAYER_SIZES))
    payload = SubmissionPayload(
        group_id=str(item["group_id"]),
        username=str(item["username"]),
        weights=item["weights"],
        biases=item["biases"],
    )
    apply_weight_payload(car, payload)
    car.set_collision_surface(track.collision)
    spawn = track.spawn
    car.reset_state(
        spawn["x"],
        spawn["y"],
        angle=spawn["angle"],
        car_image=car_image,
    )
    return ReplayCar(item=item, car=car, color=color)


def update_replay_cars(replay_cars: list[ReplayCar]) -> None:
    for replay_car in replay_cars:
        step_replay_car(replay_car)


def step_replay_car(replay_car: ReplayCar) -> None:
    if replay_car.crashed or replay_car.stalled:
        return
    try:
        replay_car.car.update()
        if replay_car.car.collision():
            replay_car.car.collided = True
            replay_car.crashed = True
            return
        replay_car.car.feedforward()
        replay_car.car.takeAction()
        replay_car.observe_position()
    except (IndexError, pygame.error, ValueError):
        replay_car.car.collided = True
        replay_car.crashed = True


def _draw_phase_one(
    screen: pygame.Surface,
    easy: ReplaySession,
    hard: ReplaySession,
    fonts: dict[str, pygame.font.Font],
    status: str,
) -> bool:
    _draw_header(screen, fonts, "PHASE 1", status)
    easy_rect = pygame.Rect(24, 94, 764, 430)
    hard_rect = pygame.Rect(812, 94, 764, 430)
    _draw_map_panel(screen, easy, easy_rect, "EASY", EASY_ACCENT, fonts)
    _draw_map_panel(screen, hard, hard_rect, "HARD", HARD_ACCENT, fonts)
    _draw_compact_leaderboard(screen, easy, pygame.Rect(24, 554, 764, 316), EASY_ACCENT, fonts)
    _draw_compact_leaderboard(screen, hard, pygame.Rect(812, 554, 764, 316), HARD_ACCENT, fonts)
    return easy.tick() and hard.tick()


def _draw_final(
    screen: pygame.Surface,
    session: ReplaySession,
    fonts: dict[str, pygame.font.Font],
    status: str,
) -> bool:
    _draw_header(screen, fonts, "FINAL", status)
    _draw_map_panel(screen, session, pygame.Rect(24, 94, 1032, 581), "FINAL HARD MAP", FINAL_ACCENT, fonts)
    _draw_compact_leaderboard(screen, session, pygame.Rect(1080, 94, 496, 776), FINAL_ACCENT, fonts, rows=10)
    return session.tick()


def _draw_header(
    screen: pygame.Surface,
    fonts: dict[str, pygame.font.Font],
    stage: str,
    status: str,
) -> None:
    screen.blit(fonts["title"].render(f"NEURAL CARS  /  {stage}", True, TEXT), (24, 20))
    text = fonts["meta"].render(status, True, MUTED)
    screen.blit(text, (SCREEN_SIZE[0] - text.get_width() - 24, 31))
    pygame.draw.line(screen, BORDER, (24, 72), (SCREEN_SIZE[0] - 24, 72), 1)


def _draw_map_panel(
    screen: pygame.Surface,
    session: ReplaySession,
    rect: pygame.Rect,
    title: str,
    accent: Color,
    fonts: dict[str, pygame.font.Font],
) -> None:
    pygame.draw.rect(screen, PANEL, rect.inflate(0, 0))
    pygame.draw.rect(screen, BORDER, rect, 1)
    native = session.track.front.copy()
    for replay_car in session.cars:
        color = DIM_COLOR if replay_car.crashed or replay_car.stalled else replay_car.color
        replay_car.car.draw(native)
        pygame.draw.circle(native, color, (int(replay_car.car.x), int(replay_car.car.y)), 7)
    scaled = pygame.transform.smoothscale(native, rect.size)
    screen.blit(scaled, rect.topleft)
    pygame.draw.rect(screen, BORDER, rect, 1)
    pygame.draw.rect(screen, BACKGROUND, (rect.x, rect.y, 134, 30))
    pygame.draw.rect(screen, accent, (rect.x, rect.y, 4, 30))
    screen.blit(fonts["panel"].render(title, True, TEXT), (rect.x + 12, rect.y + 6))
    occupied_labels: list[pygame.Rect] = []
    for replay_car in session.cars:
        color = DIM_COLOR if replay_car.crashed or replay_car.stalled else replay_car.color
        x = rect.x + int(replay_car.car.x / SCREEN_SIZE[0] * rect.width)
        y = rect.y + int(replay_car.car.y / SCREEN_SIZE[1] * rect.height)
        label = fonts["label"].render(replay_car.label, True, color)
        label_x, label_y = _place_label(rect, x, y, label, occupied_labels)
        screen.blit(label, (label_x, label_y))
        occupied_labels.append(pygame.Rect(label_x, label_y, label.get_width(), label.get_height()))


def _draw_compact_leaderboard(
    screen: pygame.Surface,
    session: ReplaySession,
    rect: pygame.Rect,
    accent: Color,
    fonts: dict[str, pygame.font.Font],
    *,
    rows: int = 5,
) -> None:
    pygame.draw.rect(screen, PANEL, rect)
    pygame.draw.rect(screen, BORDER, rect, 1)
    screen.blit(fonts["panel"].render("LEADERBOARD", True, TEXT), (rect.x + 14, rect.y + 13))
    pygame.draw.line(screen, accent, (rect.x + 14, rect.y + 43), (rect.right - 14, rect.y + 43), 2)
    if not session.leaderboard:
        screen.blit(fonts["meta"].render("Waiting for completed submissions", True, MUTED), (rect.x + 14, rect.y + 62))
        return
    y = rect.y + 60
    for entry in session.leaderboard[:rows]:
        client_result = entry["client_result"]
        identity = f"Group {entry['group_id']}" if session.competition_id == "final" else entry["username"]
        detail = entry["username"] if session.competition_id == "final" else f"G{entry['group_id']}"
        screen.blit(fonts["row"].render(f"#{entry['rank']}", True, accent), (rect.x + 14, y))
        screen.blit(fonts["row"].render(identity, True, TEXT), (rect.x + 60, y))
        screen.blit(fonts["meta"].render(detail, True, MUTED), (rect.x + 60, y + 21))
        result = _result_text(client_result)
        rendered = fonts["row"].render(result, True, TEXT)
        screen.blit(rendered, (rect.right - rendered.get_width() - 14, y + 7))
        y += 48


def _draw_phase_one_waiting(screen: pygame.Surface, fonts: dict[str, pygame.font.Font], status: str) -> None:
    _draw_header(screen, fonts, "PHASE 1", status)
    _draw_centered(screen, fonts["title"], "Waiting for Easy and Hard replay data", 450)


def _draw_final_waiting(screen: pygame.Surface, fonts: dict[str, pygame.font.Font], status: str) -> None:
    _draw_header(screen, fonts, "FINAL", status)
    _draw_centered(screen, fonts["title"], "Waiting for Final replay data", 450)


def _draw_centered(screen: pygame.Surface, font: pygame.font.Font, text: str, y: int) -> None:
    rendered = font.render(text, True, MUTED)
    screen.blit(rendered, ((SCREEN_SIZE[0] - rendered.get_width()) // 2, y))


def _place_label(
    rect: pygame.Rect,
    x: int,
    y: int,
    label: pygame.Surface,
    occupied: list[pygame.Rect],
) -> tuple[int, int]:
    label_x = min(max(rect.x + 4, x + 8), rect.right - label.get_width() - 4)
    height = label.get_height()
    candidates = [y - height - 8]
    candidates.extend(y - height - 8 - (step * (height + 2)) for step in range(1, 16))
    candidates.extend(y + 10 + (step * (height + 2)) for step in range(16))

    for candidate_y in candidates:
        candidate = pygame.Rect(label_x, candidate_y, label.get_width(), height)
        if candidate.top < rect.y + 32 or candidate.bottom > rect.bottom - 4:
            continue
        if not any(candidate.colliderect(other) for other in occupied):
            return candidate.x, candidate.y
    return label_x, max(rect.y + 32, min(y - height - 8, rect.bottom - height - 4))


def _result_text(client_result: dict[str, Any]) -> str:
    if client_result.get("completed"):
        ticks = int(client_result["lap_ticks"])
        return f"{ticks / FPS:.1f}s"
    return f"{float(client_result['max_progress']):.0f} prog"


def _fonts() -> dict[str, pygame.font.Font]:
    return {
        "title": pygame.font.SysFont("Arial", 28, bold=True),
        "panel": pygame.font.SysFont("Arial", 18, bold=True),
        "row": pygame.font.SysFont("Arial", 17, bold=True),
        "label": pygame.font.SysFont("Arial", 15, bold=True),
        "meta": pygame.font.SysFont("Arial", 14),
    }
