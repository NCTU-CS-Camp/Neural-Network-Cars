from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pygame

from game_engine.backend.assets import GameAssets, load_game_assets
from game_engine.backend.car import Car
from game_engine.backend.competition_track import CompetitionRunTracker
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
LeaderboardSignature = tuple[tuple[int, str], ...]
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
REPLAY_HOLD_SECONDS = 3.0
REPLAY_FETCH_SECONDS = 5.0
LEADERBOARD_REVEAL_HIGHLIGHT_SECONDS = 2.0
VIRTUAL_SIZE = SCREEN_SIZE
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
    tracker: CompetitionRunTracker
    crashed: bool = False
    finished: bool = False
    finish_ticks: int | None = None
    stalled: bool = False
    ticks: int = 0
    stagnation_ticks: int = 0
    last_progress_position: tuple[float, float] | None = None

    def __post_init__(self) -> None:
        self.last_progress_position = (float(self.car.x), float(self.car.y))

    @property
    def label(self) -> str:
        state = ""
        if self.finished:
            if self.finish_ticks is not None:
                state = f" FINISHED {self.finish_ticks / FPS:.3f}s"
            else:
                state = " FINISHED"
        elif self.stalled:
            state = " STALLED"
        elif self.crashed:
            state = " CRASHED"
        return f"{self.item.get('username', 'unknown')}{state}"

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
    leaderboard_signature: LeaderboardSignature = ()
    leaderboard_revealed: bool = False
    reveal_highlight_until: float = 0.0
    frame_limit: int = FRAME_LIMIT
    frames: int = 0
    stopped: bool = False

    @property
    def has_cars(self) -> bool:
        return bool(self.cars)

    def tick(self) -> bool:
        if self.stopped:
            return True
        if not self.cars:
            self.stopped = True
            return True
        update_replay_cars(self.cars)
        self.frames += 1
        self.stopped = (
            all(
                replay_car.crashed or replay_car.stalled or replay_car.finished
                for replay_car in self.cars
            )
        ) or self.frames >= self.frame_limit
        return self.stopped


@dataclass(frozen=True, slots=True)
class ReplayStatus:
    label: str
    elapsed_seconds: float = 0.0
    restart_seconds: float | None = None
    snapshot_countdown: str = "-"


def run(
    server_url: str | None = None,
    token: str | None = None,
) -> None:
    pygame.init()
    display = create_replay_display()
    virtual_screen = pygame.Surface(VIRTUAL_SIZE)
    window_size = VIRTUAL_SIZE
    windowed_size = VIRTUAL_SIZE
    fullscreen = False
    pygame.display.set_caption("Neural Cars Competition Replay")
    clock = pygame.time.Clock()
    fonts = _fonts()
    assets = load_game_assets()
    replay_token = token or os.environ.get("COMPETITION_REPLAY_TOKEN", "admin")
    replay_url = server_url or os.environ.get(
        "COMPETITION_SERVER_URL", "http://127.0.0.1:8000"
    )

    state: dict[str, Any] | None = None
    pending_state: dict[str, Any] | None = None
    sessions: dict[str, ReplaySession] = {}
    revealed_signatures: dict[str, LeaderboardSignature] = {}
    next_fetch_at = 0.0
    status = "Connecting to protected replay feed"
    hold_until: float | None = None

    try:
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
                if event.type == pygame.VIDEORESIZE and not fullscreen:
                    window_size = (max(1, event.w), max(1, event.h))
                    windowed_size = window_size
                    display = create_replay_display(window_size)
                    pygame.display.set_caption("Neural Cars Competition Replay")
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_f:
                        fullscreen = not fullscreen
                        if fullscreen:
                            windowed_size = window_size
                            display = create_replay_display(fullscreen=True)
                            window_size = display.get_size()
                        else:
                            window_size = windowed_size
                            display = create_replay_display(window_size)
                        pygame.display.set_caption("Neural Cars Competition Replay")
                    elif event.key == pygame.K_r:
                        fullscreen = False
                        window_size = VIRTUAL_SIZE
                        windowed_size = VIRTUAL_SIZE
                        display = create_replay_display(window_size)
                        pygame.display.set_caption("Neural Cars Competition Replay")
                    elif event.key == pygame.K_ESCAPE:
                        if fullscreen:
                            fullscreen = False
                            window_size = windowed_size
                            display = create_replay_display(window_size)
                            pygame.display.set_caption("Neural Cars Competition Replay")
                        else:
                            return

            now = time.monotonic()
            if now >= next_fetch_at:
                try:
                    incoming_state = fetch_replay_state(replay_url, replay_token)
                    next_fetch_at = now + REPLAY_FETCH_SECONDS
                    if state is None:
                        state = incoming_state
                        sessions = load_replay_sessions(
                            state,
                            assets,
                            revealed_signatures,
                        )
                        pending_state = None
                        hold_until = None
                    elif _replay_payload_identity(incoming_state) != _replay_payload_identity(state):
                        if _has_runnable_sessions(sessions):
                            pending_state = incoming_state
                        else:
                            state = incoming_state
                            sessions = load_replay_sessions(
                                state,
                                assets,
                                revealed_signatures,
                            )
                            pending_state = None
                            hold_until = None
                    else:
                        state = incoming_state
                        pending_state = None
                    status = "RUNNING"
                except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
                    status = f"Replay feed unavailable: {exc}"
                    next_fetch_at = now + REPLAY_FETCH_SECONDS

            virtual_screen.fill(BACKGROUND)
            if state is None:
                _draw_centered(
                    virtual_screen,
                    fonts["title"],
                    status,
                    SCREEN_SIZE[1] // 2,
                )
            elif state.get("stage") == "final":
                session = sessions.get("final")
                if session is not None:
                    display_status = _replay_status(
                        "FINAL",
                        (session,),
                        state,
                        now,
                        hold_until,
                    )
                    finished = _draw_final(
                        virtual_screen,
                        session,
                        fonts,
                        display_status,
                        now,
                        revealed_signatures,
                    )
                    hold_until, cycle_done = _handle_finished_cycle(
                        finished,
                        now,
                        hold_until,
                    )
                    if cycle_done:
                        state, sessions, pending_state, hold_until = _start_next_replay_cycle(
                            state,
                            pending_state,
                            assets,
                            revealed_signatures,
                        )
                else:
                    _draw_final_waiting(
                        virtual_screen,
                        fonts,
                        _waiting_status_text(state),
                    )
                    next_fetch_at = now + 3.0
            else:
                easy = sessions.get("easy")
                hard = sessions.get("hard")
                if easy is not None and hard is not None:
                    runnable_sessions = _runnable_sessions(easy, hard)
                    if runnable_sessions:
                        display_status = _replay_status(
                            _phase_one_stage_label(runnable_sessions),
                            runnable_sessions,
                            state,
                            now,
                            hold_until,
                        )
                    else:
                        display_status = _waiting_status_text(state)
                    finished = _draw_phase_one(
                        virtual_screen,
                        easy,
                        hard,
                        fonts,
                        display_status,
                        now,
                        revealed_signatures,
                    )
                    if runnable_sessions:
                        hold_until, cycle_done = _handle_finished_cycle(
                            finished,
                            now,
                            hold_until,
                        )
                        if cycle_done:
                            state, sessions, pending_state, hold_until = _start_next_replay_cycle(
                                state,
                                pending_state,
                                assets,
                                revealed_signatures,
                            )
                    else:
                        hold_until = None
                        if now >= next_fetch_at:
                            sessions.clear()
                            state = None
                            next_fetch_at = now + 3.0
                else:
                    _draw_phase_one_waiting(
                        virtual_screen,
                        fonts,
                        _waiting_status_text(state),
                    )
                    next_fetch_at = now + 3.0

            scale_virtual_screen(virtual_screen, display, window_size)
            pygame.display.flip()
            clock.tick(FPS)
    finally:
        pygame.quit()


def create_replay_display(
    window_size: tuple[int, int] = VIRTUAL_SIZE,
    *,
    fullscreen: bool = False,
) -> pygame.Surface:
    flags = pygame.FULLSCREEN if fullscreen else pygame.RESIZABLE
    size = (0, 0) if fullscreen else window_size
    return pygame.display.set_mode(size, flags)


def scaled_rect_for_window(window_size: tuple[int, int]) -> pygame.Rect:
    window_width = max(1, window_size[0])
    window_height = max(1, window_size[1])
    scale = min(
        window_width / VIRTUAL_SIZE[0],
        window_height / VIRTUAL_SIZE[1],
    )
    width = max(1, round(VIRTUAL_SIZE[0] * scale))
    height = max(1, round(VIRTUAL_SIZE[1] * scale))
    x = (window_width - width) // 2
    y = (window_height - height) // 2
    return pygame.Rect(x, y, width, height)


def scale_virtual_screen(
    virtual_screen: pygame.Surface,
    display: pygame.Surface,
    window_size: tuple[int, int],
) -> pygame.Rect:
    rect = scaled_rect_for_window(window_size)
    display.fill(BACKGROUND)
    scaled = pygame.transform.smoothscale(virtual_screen, rect.size)
    display.blit(scaled, rect)
    return rect


def fetch_replay_state(server_url: str, token: str) -> dict[str, Any]:
    request = Request(
        server_url.rstrip("/") + "/v2/admin/replay",
        headers={"X-Admin-Token": token},
        method="GET",
    )
    with urlopen(request, timeout=5.0) as response:
        return json.loads(response.read().decode("utf-8"))


def _replay_status(
    stage: str,
    sessions: tuple[ReplaySession, ...],
    state: dict[str, Any],
    now: float,
    hold_until: float | None,
) -> ReplayStatus:
    elapsed = max((session.frames for session in sessions), default=0) / FPS
    snapshot = _snapshot_countdown_text(state)
    if hold_until is not None:
        remaining = max(0.0, hold_until - now)
        return ReplayStatus(
            label=f"Replay complete / {stage}",
            elapsed_seconds=elapsed,
            restart_seconds=remaining,
            snapshot_countdown=snapshot,
        )
    return ReplayStatus(
        label=f"Running replay / {stage}",
        elapsed_seconds=elapsed,
        snapshot_countdown=snapshot,
    )


def _runnable_sessions(*sessions: ReplaySession) -> tuple[ReplaySession, ...]:
    return tuple(session for session in sessions if session.has_cars)


def _phase_one_stage_label(sessions: tuple[ReplaySession, ...]) -> str:
    names = " + ".join(session.competition_id.upper() for session in sessions)
    return f"Phase 1 / {names}" if names else "Phase 1 / Waiting"


def _waiting_status_text(state: dict[str, Any]) -> ReplayStatus:
    return ReplayStatus(
        label="Waiting for submissions",
        snapshot_countdown=_snapshot_countdown_text(state),
    )


def _snapshot_countdown_text(state: dict[str, Any]) -> str:
    if state.get("stage") == "final":
        return "-"
    target = state.get("config", {}).get("next_phase_one_batch_at")
    if not target:
        return "-"
    try:
        target_time = datetime.fromisoformat(str(target))
    except ValueError:
        return "-"
    remaining = max(0.0, target_time.timestamp() - time.time())
    minutes = int(remaining // 60)
    seconds = int(remaining % 60)
    return f"{minutes}:{seconds:02d}"


def leaderboard_signature(leaderboard: list[dict[str, Any]]) -> LeaderboardSignature:
    return tuple(
        (int(entry.get("rank", 0)), str(entry.get("submission_id", "")))
        for entry in leaderboard
    )


def _replay_payload_signatures(state: dict[str, Any]) -> tuple[tuple[str, LeaderboardSignature], ...]:
    return tuple(
        sorted(
            (
                str(competition_id),
                leaderboard_signature(list(replay.get("leaderboard", []))),
            )
            for competition_id, replay in state.get("replays", {}).items()
        )
    )


def _replay_payload_identity(state: dict[str, Any]) -> tuple[str, int, tuple[tuple[str, LeaderboardSignature], ...]]:
    return (
        str(state.get("stage", "")),
        int(state.get("replay_generation", 0)),
        _replay_payload_signatures(state),
    )


def _has_runnable_sessions(sessions: dict[str, ReplaySession]) -> bool:
    return any(session.has_cars for session in sessions.values())


def _handle_finished_cycle(
    finished: bool,
    now: float,
    hold_until: float | None,
) -> tuple[float | None, bool]:
    if not finished:
        return None, False
    if hold_until is None:
        return now + REPLAY_HOLD_SECONDS, False
    if now < hold_until:
        return hold_until, False
    return None, True


def _start_next_replay_cycle(
    state: dict[str, Any] | None,
    pending_state: dict[str, Any] | None,
    assets: GameAssets,
    revealed_signatures: dict[str, LeaderboardSignature],
) -> tuple[dict[str, Any] | None, dict[str, ReplaySession], dict[str, Any] | None, None]:
    next_state = pending_state or state
    if next_state is None:
        return None, {}, None, None
    return (
        next_state,
        load_replay_sessions(next_state, assets, revealed_signatures),
        None,
        None,
    )


def load_replay_sessions(
    state: dict[str, Any],
    assets: GameAssets,
    revealed_signatures: dict[str, LeaderboardSignature] | None = None,
) -> dict[str, ReplaySession]:
    sessions = {}
    for competition_id, replay in state.get("replays", {}).items():
        sessions[competition_id] = load_replay_session(
            competition_id,
            replay,
            assets,
            revealed_signatures or {},
        )
    return sessions


def load_replay_session(
    competition_id: str,
    replay: dict[str, Any],
    assets: GameAssets,
    revealed_signatures: dict[str, LeaderboardSignature] | None = None,
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
    leaderboard = list(replay.get("leaderboard", []))
    signature = leaderboard_signature(leaderboard)
    is_revealed = (
        not signature
        or not cars
        or signature == (revealed_signatures or {}).get(competition_id)
    )
    return ReplaySession(
        competition_id=competition_id,
        track=track,
        cars=cars,
        leaderboard=leaderboard,
        leaderboard_signature=signature,
        leaderboard_revealed=is_revealed,
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
    tracker = CompetitionRunTracker.from_metadata_path(track.competition_map.metadata_path)
    return ReplayCar(item=item, car=car, color=color, tracker=tracker)


def update_replay_cars(replay_cars: list[ReplayCar]) -> None:
    for replay_car in replay_cars:
        step_replay_car(replay_car)


def step_replay_car(replay_car: ReplayCar) -> None:
    if replay_car.crashed or replay_car.stalled or replay_car.finished:
        return
    try:
        previous = (float(replay_car.car.x), float(replay_car.car.y))
        replay_car.car.update()
        replay_car.ticks += 1
        if replay_car.car.collision():
            replay_car.car.collided = True
            replay_car.crashed = True
            return
        current = (float(replay_car.car.x), float(replay_car.car.y))
        replay_car.tracker.advance(previous, current, tick=replay_car.ticks)
        if replay_car.tracker.completed:
            replay_car.finished = True
            replay_car.finish_ticks = replay_car.tracker.lap_ticks
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
    status: ReplayStatus,
    now: float,
    revealed_signatures: dict[str, LeaderboardSignature],
) -> bool:
    _draw_header(screen, fonts, "PHASE 1", status)
    easy_rect = pygame.Rect(24, 136, 764, 390)
    hard_rect = pygame.Rect(812, 136, 764, 390)
    _draw_map_panel(screen, easy, easy_rect, "EASY", EASY_ACCENT, fonts)
    _draw_map_panel(screen, hard, hard_rect, "HARD", HARD_ACCENT, fonts)
    _draw_compact_leaderboard(
        screen,
        easy,
        pygame.Rect(24, 554, 764, 316),
        EASY_ACCENT,
        fonts,
        now=now,
    )
    _draw_compact_leaderboard(
        screen,
        hard,
        pygame.Rect(812, 554, 764, 316),
        HARD_ACCENT,
        fonts,
        now=now,
    )
    easy_finished = easy.tick()
    hard_finished = hard.tick()
    _reveal_leaderboard_if_stopped(easy, now, revealed_signatures)
    _reveal_leaderboard_if_stopped(hard, now, revealed_signatures)
    return easy_finished and hard_finished


def _draw_final(
    screen: pygame.Surface,
    session: ReplaySession,
    fonts: dict[str, pygame.font.Font],
    status: ReplayStatus,
    now: float,
    revealed_signatures: dict[str, LeaderboardSignature],
) -> bool:
    _draw_header(screen, fonts, "FINAL", status)
    _draw_map_panel(
        screen,
        session,
        pygame.Rect(24, 136, 1032, 540),
        "FINAL HARD MAP",
        FINAL_ACCENT,
        fonts,
    )
    _draw_compact_leaderboard(
        screen,
        session,
        pygame.Rect(1080, 136, 496, 734),
        FINAL_ACCENT,
        fonts,
        rows=10,
        now=now,
    )
    finished = session.tick()
    _reveal_leaderboard_if_stopped(session, now, revealed_signatures)
    return finished


def _draw_header(
    screen: pygame.Surface,
    fonts: dict[str, pygame.font.Font],
    stage: str,
    status: ReplayStatus,
) -> None:
    screen.blit(fonts["title"].render(f"NEURAL CARS  /  {stage}", True, TEXT), (24, 20))
    bar = pygame.Rect(24, 58, SCREEN_SIZE[0] - 48, 54)
    pygame.draw.rect(screen, PANEL, bar)
    pygame.draw.rect(screen, BORDER, bar, 1)
    pygame.draw.rect(screen, EASY_ACCENT, (bar.x, bar.y, 5, bar.height))
    screen.blit(fonts["status"].render(status.label, True, TEXT), (bar.x + 18, bar.y + 10))
    chip_x = bar.right - 18
    chips = [
        f"Elapsed {status.elapsed_seconds:.1f}s",
        f"Next replay {status.restart_seconds:.0f}s"
        if status.restart_seconds is not None
        else "Next replay -",
        f"Next snapshot {status.snapshot_countdown}",
    ]
    for text in reversed(chips):
        chip_x = _draw_status_chip(screen, fonts, text, chip_x, bar.centery)
    pygame.draw.line(screen, BORDER, (24, 124), (SCREEN_SIZE[0] - 24, 124), 1)


def _draw_status_chip(
    screen: pygame.Surface,
    fonts: dict[str, pygame.font.Font],
    text: str,
    right: int,
    center_y: int,
) -> int:
    rendered = fonts["chip"].render(text, True, TEXT)
    chip = pygame.Rect(0, 0, rendered.get_width() + 22, 34)
    chip.right = right
    chip.centery = center_y
    pygame.draw.rect(screen, BACKGROUND, chip, border_radius=4)
    pygame.draw.rect(screen, BORDER, chip, 1, border_radius=4)
    screen.blit(rendered, (chip.x + 11, chip.y + 7))
    return chip.x - 10


def _draw_map_panel(
    screen: pygame.Surface,
    session: ReplaySession,
    rect: pygame.Rect,
    title: str,
    accent: Color,
    fonts: dict[str, pygame.font.Font],
) -> None:
    panel_status = replay_panel_status(session)
    pygame.draw.rect(screen, PANEL, rect.inflate(0, 0))
    native = session.track.front.copy()
    for replay_car in session.cars:
        color = (
            DIM_COLOR
            if replay_car.crashed or replay_car.stalled or replay_car.finished
            else replay_car.color
        )
        replay_car.car.draw(native)
        pygame.draw.circle(native, color, (int(replay_car.car.x), int(replay_car.car.y)), 7)
    scaled = pygame.transform.smoothscale(native, rect.size)
    screen.blit(scaled, rect.topleft)
    border_color = accent if panel_status == "RUNNING" else BORDER
    border_width = 3 if panel_status == "RUNNING" else 1
    pygame.draw.rect(screen, border_color, rect, border_width)
    pygame.draw.rect(screen, BACKGROUND, (rect.x, rect.y, 134, 30))
    pygame.draw.rect(screen, accent, (rect.x, rect.y, 4, 30))
    screen.blit(fonts["panel"].render(title, True, TEXT), (rect.x + 12, rect.y + 6))
    _draw_panel_badge(screen, rect, panel_status, accent, fonts)
    if panel_status == "WAITING":
        _draw_waiting_for_submissions(screen, rect, fonts)
    for replay_car in sorted(session.cars, key=_replay_rank, reverse=True):
        color = (
            DIM_COLOR
            if replay_car.crashed or replay_car.stalled or replay_car.finished
            else replay_car.color
        )
        x = rect.x + int(replay_car.car.x / SCREEN_SIZE[0] * rect.width)
        y = rect.y + int(replay_car.car.y / SCREEN_SIZE[1] * rect.height)
        label = fonts["label"].render(replay_car.label, True, color)
        label_x, label_y = _fixed_label_position(rect, x, y, label)
        screen.blit(label, (label_x, label_y))


def _draw_compact_leaderboard(
    screen: pygame.Surface,
    session: ReplaySession,
    rect: pygame.Rect,
    accent: Color,
    fonts: dict[str, pygame.font.Font],
    *,
    rows: int = 5,
    now: float = 0.0,
) -> None:
    pygame.draw.rect(screen, PANEL, rect)
    highlighted = session.reveal_highlight_until > now
    pygame.draw.rect(screen, accent if highlighted else BORDER, rect, 3 if highlighted else 1)
    screen.blit(fonts["panel"].render("LEADERBOARD", True, TEXT), (rect.x + 14, rect.y + 13))
    pygame.draw.line(screen, accent, (rect.x + 14, rect.y + 43), (rect.right - 14, rect.y + 43), 2)
    if not session.leaderboard:
        screen.blit(fonts["meta"].render("Waiting for completed submissions", True, MUTED), (rect.x + 14, rect.y + 62))
        return
    if not session.leaderboard_revealed:
        _draw_leaderboard_reveal_panel(screen, session, rect, accent, fonts)
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


def _draw_leaderboard_reveal_panel(
    screen: pygame.Surface,
    session: ReplaySession,
    rect: pygame.Rect,
    accent: Color,
    fonts: dict[str, pygame.font.Font],
) -> None:
    title = fonts["panel"].render("New snapshot replay running", True, TEXT)
    subtitle = fonts["meta"].render("Leaderboard reveals after this replay", True, MUTED)
    elapsed = fonts["chip"].render(f"Elapsed {session.frames / FPS:.1f}s", True, TEXT)
    box = pygame.Rect(0, 0, min(rect.width - 52, 390), 132)
    box.center = rect.center
    pygame.draw.rect(screen, BACKGROUND, box, border_radius=6)
    pygame.draw.rect(screen, accent, box, 2, border_radius=6)
    screen.blit(title, (box.centerx - title.get_width() // 2, box.y + 24))
    screen.blit(subtitle, (box.centerx - subtitle.get_width() // 2, box.y + 58))
    screen.blit(elapsed, (box.centerx - elapsed.get_width() // 2, box.y + 91))


def _reveal_leaderboard_if_stopped(
    session: ReplaySession,
    now: float,
    revealed_signatures: dict[str, LeaderboardSignature],
) -> None:
    if not session.stopped or session.leaderboard_revealed:
        return
    session.leaderboard_revealed = True
    session.reveal_highlight_until = now + LEADERBOARD_REVEAL_HIGHLIGHT_SECONDS
    if session.leaderboard_signature:
        revealed_signatures[session.competition_id] = session.leaderboard_signature


def _draw_phase_one_waiting(
    screen: pygame.Surface,
    fonts: dict[str, pygame.font.Font],
    status: ReplayStatus,
) -> None:
    _draw_header(screen, fonts, "PHASE 1", status)
    _draw_centered(screen, fonts["title"], "Waiting for Easy and Hard replay data", 450)


def _draw_final_waiting(
    screen: pygame.Surface,
    fonts: dict[str, pygame.font.Font],
    status: ReplayStatus,
) -> None:
    _draw_header(screen, fonts, "FINAL", status)
    _draw_centered(screen, fonts["title"], "Waiting for Final replay data", 450)


def _draw_centered(screen: pygame.Surface, font: pygame.font.Font, text: str, y: int) -> None:
    rendered = font.render(text, True, MUTED)
    screen.blit(rendered, ((SCREEN_SIZE[0] - rendered.get_width()) // 2, y))


def _fixed_label_position(
    rect: pygame.Rect,
    x: int,
    y: int,
    label: pygame.Surface,
) -> tuple[int, int]:
    height = label.get_height()
    min_x = rect.x + 4
    min_y = rect.y + 32
    max_x = max(min_x, rect.right - label.get_width() - 4)
    max_y = max(min_y, rect.bottom - height - 4)
    label_x = min(max(min_x, x + 8), max_x)
    label_y = min(max(min_y, y - height - 8), max_y)
    return label_x, label_y


def _replay_rank(replay_car: ReplayCar) -> int:
    try:
        return int(replay_car.item.get("rank", 9999))
    except (TypeError, ValueError):
        return 9999


def replay_panel_status(session: ReplaySession) -> str:
    if not session.has_cars:
        return "WAITING"
    if session.stopped:
        return "COMPLETE"
    return "RUNNING"


def _draw_panel_badge(
    screen: pygame.Surface,
    rect: pygame.Rect,
    status: str,
    accent: Color,
    fonts: dict[str, pygame.font.Font],
) -> None:
    color = accent if status == "RUNNING" else MUTED
    label = fonts["meta"].render(status, True, TEXT if status == "RUNNING" else MUTED)
    badge = pygame.Rect(
        rect.right - label.get_width() - 24,
        rect.y + 6,
        label.get_width() + 16,
        22,
    )
    pygame.draw.rect(screen, BACKGROUND, badge)
    pygame.draw.rect(screen, color, badge, 1)
    screen.blit(label, (badge.x + 8, badge.y + 4))


def _draw_waiting_for_submissions(
    screen: pygame.Surface,
    rect: pygame.Rect,
    fonts: dict[str, pygame.font.Font],
) -> None:
    message = fonts["panel"].render("WAITING FOR SUBMISSIONS", True, MUTED)
    box = pygame.Rect(0, 0, message.get_width() + 34, 42)
    box.center = rect.center
    pygame.draw.rect(screen, BACKGROUND, box)
    pygame.draw.rect(screen, BORDER, box, 1)
    screen.blit(message, (box.x + 17, box.y + 11))


def _result_text(client_result: dict[str, Any]) -> str:
    if client_result.get("completed"):
        ticks = int(client_result["lap_ticks"])
        return f"{ticks / FPS:.3f}s"
    return f"{float(client_result['max_progress']):.0f} prog"


def _fonts() -> dict[str, pygame.font.Font]:
    def font(size: int, *, bold: bool = False) -> pygame.font.Font:
        for path in _font_path_candidates(bold=bold):
            if os.path.exists(path):
                return pygame.font.Font(path, size)
        for name in _font_name_candidates():
            matched = pygame.font.match_font(name, bold=bold)
            if matched:
                return pygame.font.Font(matched, size)
        return pygame.font.SysFont("Arial", size, bold=bold)

    return {
        "title": font(28, bold=True),
        "status": font(30, bold=True),
        "chip": font(20, bold=True),
        "panel": font(18, bold=True),
        "row": font(17, bold=True),
        "label": font(15, bold=True),
        "meta": font(14),
    }


def _font_path_candidates(*, bold: bool) -> list[str]:
    configured = os.environ.get("COMPETITION_REPLAY_FONT_PATH")
    candidates = [
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Supplemental/Songti.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/arphic/uming.ttc",
        "/usr/share/fonts/truetype/arphic/ukai.ttc",
        "C:/Windows/Fonts/msjh.ttc",
        "C:/Windows/Fonts/msjhbd.ttc",
    ]
    if bold:
        candidates = sorted(candidates, key=lambda path: "Bold" not in path and "bd" not in path)
    if configured:
        return [configured, *candidates]
    return candidates


def _font_name_candidates() -> list[str]:
    return [
        "hiraginosansgb",
        "stheitimedium",
        "stheitilight",
        "PingFang TC",
        "PingFang HK",
        "PingFang SC",
        "Heiti TC",
        "Microsoft JhengHei",
        "Noto Sans CJK TC",
        "Noto Sans CJK SC",
        "Noto Sans CJK",
        "Arial Unicode MS",
        "Arial",
    ]
