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
from game_engine.backend.settings import FONT_PATH, FPS, SCREEN_SIZE
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

# ------------------------------------------------------------------ F1 "Podium Hero" palette
# Presentation-only restyle (see docs / design handoff). The legacy names
# (BACKGROUND/PANEL/BORDER/TEXT/MUTED/*_ACCENT/DIM_COLOR) are kept as aliases to the new
# values so any untouched draw code keeps working. Hex equivalents in comments.
BG_STAGE: Color = (17, 16, 23)       # #111017 main screen fill
BG_DEEP: Color = (14, 14, 21)        # #0E0E15 map wells / chip fill
PANEL: Color = (26, 26, 34)          # #1A1A22 list panels
PANEL2: Color = (30, 30, 39)         # #1E1E27 position blocks (rank 4+)
BORDER: Color = (52, 52, 62)         # #34343E outer borders
BORDER_SOFT: Color = (42, 42, 52)    # #2A2A34 inner borders
ROW_LINE: Color = (34, 34, 43)       # #22222B row separators

RED: Color = (225, 6, 0)             # #E10600 brand red / leader / Hard accent
RED_BRIGHT: Color = (255, 68, 56)    # #FF4438
GOLD: Color = (225, 180, 76)         # #E1B44C P1 medal / Final accent
SILVER: Color = (199, 203, 212)      # #C7CBD4 P2 medal
SILVER_TAB: Color = (184, 188, 198)  # #B8BCC6 Easy accent
BRONZE: Color = (205, 127, 50)       # #CD7F32 P3 medal
WHITE: Color = (244, 244, 247)       # #F4F4F7 primary text
OFFWHITE: Color = (237, 237, 240)    # #EDEDF0
MUTED2: Color = (154, 154, 165)      # #9A9AA5 secondary text
DIM: Color = (92, 105, 116)          # #5C6974 finished/crashed/stalled
DARK_TEXT: Color = (8, 8, 12)        # #08080C text on light/red/gold fills

# legacy aliases (keep existing references valid)
BACKGROUND: Color = BG_STAGE
TEXT: Color = WHITE
MUTED: Color = (139, 139, 150)       # #8B8B96 labels
EASY_ACCENT: Color = SILVER_TAB
HARD_ACCENT: Color = RED
FINAL_ACCENT: Color = GOLD
DIM_COLOR: Color = DIM

# per-competition accent: Easy silver / Hard red / Final gold
ACCENT: dict[str, Color] = {"easy": SILVER_TAB, "hard": RED, "final": GOLD}
# car marker ramp by replay-rank order (dim overrides when a car is not running)
CAR_RAMP: list[Color] = [RED, OFFWHITE, SILVER, GOLD, (142, 145, 153), RED_BRIGHT]

REPLAY_PROGRESS_DISTANCE_PX = 24.0
REPLAY_HOLD_SECONDS = 3.0
REPLAY_FETCH_SECONDS = 5.0
LEADERBOARD_REVEAL_HIGHLIGHT_SECONDS = 2.0
VIRTUAL_SIZE = SCREEN_SIZE
# per-car body colors, cycled from the marker ramp (assigned by rank index at load time)
REPLAY_COLORS: list[Color] = [CAR_RAMP[index % len(CAR_RAMP)] for index in range(15)]


def medal(position: int) -> Color:
    """Medal color for a 1-based finishing position."""
    return {1: GOLD, 2: SILVER, 3: BRONZE}.get(position, MUTED)


def podium_bg(position: int) -> Color:
    """Tinted card background for a 1-based podium position."""
    return {1: (33, 29, 20), 2: (29, 30, 33), 3: (31, 23, 18)}.get(position, PANEL)


def mix(a: Color, b: Color, t: float) -> Color:
    """Blend a->b by t (0..1); used for pseudo-alpha ghost numerals over a card bg."""
    return (
        round(a[0] + (b[0] - a[0]) * t),
        round(a[1] + (b[1] - a[1]) * t),
        round(a[2] + (b[2] - a[2]) * t),
    )


def pulse_alpha(period: float = 1.1) -> float:
    """0.22..1.0 sine pulse for LIVE / SNAPSHOT dots, driven off the wall clock."""
    phase = (time.monotonic() % period) / period
    return 0.22 + 0.78 * (0.5 + 0.5 * math.cos(2 * math.pi * phase))


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
    config = state.get("config", {})
    target = config.get("next_snapshot_at") or config.get("next_phase_one_batch_at")
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


# ------------------------------------------------------------------ F1 draw helpers
def _entry_tag(entry: dict[str, Any], competition_id: str) -> str:
    """Broadcast-style short tag. Final shows the group; otherwise the first 3 ascii-alnum
    chars of the username, falling back to the group when a name has none (e.g. all-CJK)."""
    if competition_id == "final":
        return f"G{entry.get('group_id', '?')}"
    alnum = "".join(ch for ch in str(entry.get("username", "")) if ch.isascii() and ch.isalnum())
    return alnum[:3].upper() or f"G{entry.get('group_id', '?')}"


def _entry_result(client_result: dict[str, Any]) -> tuple[str, str]:
    """(value, unit) for a podium/tower result: lap seconds when completed, else progress."""
    if client_result.get("completed"):
        return f"{int(client_result['lap_ticks']) / FPS:.3f}", "SEC"
    return f"{float(client_result['max_progress']):.0f}", "PROG"


def _user_font(
    fonts: dict[str, pygame.font.Font], text: str, ascii_key: str, cjk_key: str
) -> pygame.font.Font:
    """Pick the F1 ascii face for latin text, or the CJK-capable face otherwise."""
    return fonts[ascii_key] if str(text).isascii() else fonts[cjk_key]


def _blit_clipped(
    screen: pygame.Surface, surface: pygame.Surface, x: int, y: int, max_width: int
) -> None:
    """Blit text left-aligned, hard-clipped to max_width (no ellipsis; broadcast style)."""
    previous = screen.get_clip()
    screen.set_clip(pygame.Rect(x, y, max_width, surface.get_height()))
    screen.blit(surface, (x, y))
    screen.set_clip(previous)


def _draw_pulse_dot(
    screen: pygame.Surface, cx: int, cy: int, color: Color, bg: Color, radius: int = 4
) -> None:
    """Live/snapshot indicator dot that fades over ~1.1s against a known background."""
    pygame.draw.circle(screen, mix(bg, color, pulse_alpha()), (cx, cy), radius)


def _draw_skew_banner(
    screen: pygame.Surface,
    x: int,
    y: int,
    text: str,
    accent: Color,
    font: pygame.font.Font,
    *,
    fg: Color = DARK_TEXT,
    skew: int = 10,
    padx: int = 22,
    pady: int = 8,
) -> int:
    """Angled F1 banner (EASY / HARD / FINAL, or a small car tag). Returns its total width."""
    label = font.render(text, True, fg)
    width = label.get_width() + padx * 2
    height = label.get_height() + pady * 2
    points = [(x + skew, y), (x + width + skew, y), (x + width, y + height), (x, y + height)]
    pygame.draw.polygon(screen, accent, points)
    screen.blit(label, (x + padx + skew // 2, y + pady))
    return width + skew


def _draw_ghost_numeral(
    screen: pygame.Surface,
    right: int,
    top: int,
    position: int,
    card_bg: Color,
    font: pygame.font.Font,
) -> None:
    """Giant translucent position numeral bleeding off the top-right of a podium card.
    Pygame can't alpha-blend text over an opaque bg, so blend medal->card_bg (~14%)."""
    glyph = font.render(str(position), True, mix(medal(position), card_bg, 0.86))
    screen.blit(glyph, (right - glyph.get_width() + 6, top - 16))


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
    # Two symmetric columns (design PHASE1): map on top, then podium band + tower + footer.
    # Accent is fixed by column (left = Easy silver, right = Hard red), not the session id.
    for session, col_x, title, accent in (
        (easy, 34, "EASY", ACCENT["easy"]),
        (hard, 813, "HARD", ACCENT["hard"]),
    ):
        _draw_map_panel(screen, session, pygame.Rect(col_x, 96, 753, 352), title, accent, fonts)
        _draw_compact_leaderboard(
            screen,
            session,
            pygame.Rect(col_x, 462, 753, 408),
            accent,
            fonts,
            rows=5,
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
    accent = ACCENT["final"]
    # Final (design FINAL): one large map on the left, stacked podium + tower on the right.
    _draw_map_panel(screen, session, pygame.Rect(34, 96, 940, 640), "FINAL", accent, fonts)
    _draw_compact_leaderboard(
        screen,
        session,
        pygame.Rect(1000, 96, 566, 774),
        accent,
        fonts,
        rows=7,
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
    is_final = stage == "FINAL"
    header_accent = GOLD if is_final else RED
    # skewed "N" logo tile + wordmark
    tile = pygame.Rect(34, 22, 54, 54)
    pygame.draw.polygon(
        screen,
        RED,
        [
            (tile.x + 10, tile.y),
            (tile.right + 10, tile.y),
            (tile.right, tile.bottom),
            (tile.x, tile.bottom),
        ],
    )
    glyph = fonts["banner"].render("N", True, WHITE)
    screen.blit(
        glyph,
        (tile.centerx - glyph.get_width() // 2 + 3, tile.centery - glyph.get_height() // 2),
    )
    screen.blit(fonts["wordmark"].render("NEURAL CARS", True, WHITE), (104, 24))
    sub = "FINAL · CHAMPIONSHIP" if is_final else f"{stage} · LIVE REPLAY"
    screen.blit(fonts["stage"].render(sub, True, header_accent), (104, 56))
    # right-side outlined timing chips (SNAPSHOT is a live/pulsing red chip)
    restart = f"{status.restart_seconds:.0f}s" if status.restart_seconds is not None else "—"
    chips = [
        ("ELAPSED", f"{status.elapsed_seconds:.1f}s", False),
        ("NEXT REPLAY", restart, False),
        ("SNAPSHOT", status.snapshot_countdown, True),
    ]
    chip_x = 1566
    for label, value, live in reversed(chips):
        chip_x = _draw_status_chip(screen, fonts, label, value, chip_x, 49, live=live)
    pygame.draw.line(screen, BORDER_SOFT, (34, 90), (1566, 90), 1)


def _draw_status_chip(
    screen: pygame.Surface,
    fonts: dict[str, pygame.font.Font],
    label: str,
    value: str,
    right: int,
    center_y: int,
    *,
    live: bool = False,
) -> int:
    lab = fonts["chip_label"].render(label, True, WHITE if live else MUTED)
    val = fonts["chip_value"].render(value, True, WHITE)
    dot_w = 16 if live else 0
    inner = 12 + dot_w + lab.get_width() + 8 + val.get_width() + 14
    chip = pygame.Rect(0, 0, inner, 34)
    chip.right = right
    chip.centery = center_y
    pygame.draw.rect(screen, BG_DEEP, chip)
    pygame.draw.rect(screen, RED if live else BORDER, chip, 1)
    ox = chip.x + 12
    if live:
        _draw_pulse_dot(screen, ox + 4, chip.centery, RED, BG_DEEP, 4)
        ox += dot_w
    screen.blit(lab, (ox, chip.centery - lab.get_height() // 2))
    ox += lab.get_width() + 8
    screen.blit(val, (ox, chip.centery - val.get_height() // 2))
    return chip.x - 12


def _draw_map_panel(
    screen: pygame.Surface,
    session: ReplaySession,
    rect: pygame.Rect,
    title: str,
    accent: Color,
    fonts: dict[str, pygame.font.Font],
) -> None:
    panel_status = replay_panel_status(session)
    # darkened track image (design: map darkened ~34% under an F1 dark wash)
    native = session.track.front.copy()
    wash = pygame.Surface(native.get_size(), pygame.SRCALPHA)
    wash.fill((8, 8, 12, 92))
    native.blit(wash, (0, 0))
    scaled = pygame.transform.smoothscale(native, rect.size)
    pygame.draw.rect(screen, BG_DEEP, rect)
    screen.blit(scaled, rect.topleft)
    border_color = accent if panel_status == "RUNNING" else BORDER
    pygame.draw.rect(screen, border_color, rect, 3 if panel_status == "RUNNING" else 1)
    # angled stage banner (EASY / HARD / FINAL), top-left
    banner_font = fonts["banner_fin"] if title == "FINAL" else fonts["banner"]
    _draw_skew_banner(screen, rect.x + 14, rect.y + 14, title, accent, banner_font, skew=10)
    _draw_panel_badge(screen, rect, panel_status, accent, fonts)
    if panel_status == "WAITING":
        _draw_waiting_for_submissions(screen, rect, fonts)
        return
    # car markers: colored dot + skewed tag pill; dim when not running. Best rank on top.
    native_w, native_h = native.get_size()
    for replay_car in sorted(session.cars, key=_replay_rank, reverse=True):
        running = not (replay_car.crashed or replay_car.stalled or replay_car.finished)
        ring = replay_car.color if running else DIM
        cx = rect.x + int(replay_car.car.x / native_w * rect.width)
        cy = rect.y + int(replay_car.car.y / native_h * rect.height)
        tag = _entry_tag(replay_car.item, session.competition_id)
        tag_fg = DARK_TEXT if ring in (OFFWHITE, SILVER, SILVER_TAB, GOLD) else WHITE
        _draw_skew_banner(
            screen, cx - 22, cy - 26, tag, ring, fonts["car_tag"], fg=tag_fg, skew=6, padx=7, pady=1
        )
        pygame.draw.circle(screen, DARK_TEXT, (cx, cy), 9)
        pygame.draw.circle(screen, ring, (cx, cy), 7)


def _leader_ticks(entries: list[dict[str, Any]]) -> int | None:
    """lap_ticks of rank 1 when it completed, else None (used for tower intervals)."""
    if entries:
        leader = entries[0]["client_result"]
        if leader.get("completed"):
            return int(leader["lap_ticks"])
    return None


def _draw_phase_one_podium(
    screen: pygame.Surface,
    rect: pygame.Rect,
    top3: list[dict[str, Any]],
    fonts: dict[str, pygame.font.Font],
    competition_id: str,
) -> int:
    """Three side-by-side podium cards (ghost numeral + tag + sub + medal result)."""
    gap, card_h = 8, 100
    card_w = (rect.width - 2 * gap) // 3
    for index, entry in enumerate(top3):
        pos = int(entry["rank"])
        card = pygame.Rect(rect.x + index * (card_w + gap), rect.y, card_w, card_h)
        bg = podium_bg(pos)
        pygame.draw.rect(screen, bg, card)
        pygame.draw.rect(screen, medal(pos), (card.x, card.y, card.width, 4))
        _draw_ghost_numeral(screen, card.right, card.y, pos, bg, fonts["pod_ghost"])
        screen.blit(fonts["pod_tag"].render(_entry_tag(entry, competition_id), True, WHITE), (card.x + 12, card.y + 12))
        sub = f"{entry['username']} · G{entry['group_id']}"
        sub_font = _user_font(fonts, sub, "pod_sub", "pod_sub_cjk")
        _blit_clipped(screen, sub_font.render(sub, True, MUTED2), card.x + 12, card.y + 42, card_w - 20)
        value, unit = _entry_result(entry["client_result"])
        res = fonts["pod_result"].render(value, True, medal(pos))
        screen.blit(res, (card.x + 12, card.y + 62))
        screen.blit(fonts["pod_sub"].render(unit, True, MUTED), (card.x + 12 + res.get_width() + 6, card.y + 68))
    return rect.y + card_h


def _draw_final_podium(
    screen: pygame.Surface,
    rect: pygame.Rect,
    top3: list[dict[str, Any]],
    fonts: dict[str, pygame.font.Font],
) -> int:
    """Three stacked podium cards: big medal numeral, Group N + submitter, result at right."""
    gap, card_h = 8, 66
    y = rect.y
    for entry in top3:
        pos = int(entry["rank"])
        card = pygame.Rect(rect.x, y, rect.width, card_h)
        pygame.draw.rect(screen, podium_bg(pos), card)
        pygame.draw.rect(screen, medal(pos), (card.x, card.y, 4, card.height))
        num = fonts["pod_ghost_fin"].render(str(pos), True, medal(pos))
        screen.blit(num, (card.x + 18, card.centery - num.get_height() // 2))
        screen.blit(fonts["pod_name"].render(f"Group {entry['group_id']}", True, WHITE), (card.x + 86, card.y + 10))
        uname = str(entry["username"])
        uname_font = _user_font(fonts, uname, "pod_sub", "pod_sub_cjk")
        _blit_clipped(screen, uname_font.render(uname, True, MUTED2), card.x + 86, card.y + 38, rect.width - 220)
        value, unit = _entry_result(entry["client_result"])
        res = fonts["pod_result"].render(value, True, medal(pos))
        screen.blit(res, (card.right - res.get_width() - 14, card.y + 12))
        u = fonts["pod_sub"].render(unit, True, MUTED)
        screen.blit(u, (card.right - u.get_width() - 14, card.y + 40))
        y += card_h + gap
    return y - gap


def _draw_tower_row(
    screen: pygame.Surface,
    x: int,
    y: int,
    width: int,
    entry: dict[str, Any],
    fonts: dict[str, pygame.font.Font],
    accent: Color,
    leader_ticks: int | None,
    competition_id: str,
) -> None:
    """Ranks 4..N: position block, tag, name (clipped), interval-to-leader or progress."""
    client_result = entry["client_result"]
    completed = bool(client_result.get("completed"))
    pos = int(entry["rank"])
    block = pygame.Rect(x, y + 3, 30, 24)
    pygame.draw.rect(screen, PANEL2, block)
    screen.blit(fonts["row_pos"].render(str(pos), True, MUTED), (block.x + 8, block.y + 4))
    screen.blit(fonts["row_tag"].render(_entry_tag(entry, competition_id), True, WHITE), (x + 40, y + 6))
    name = f"Group {entry['group_id']}" if competition_id == "final" else str(entry["username"])
    name_font = _user_font(fonts, name, "row_name", "row_name_cjk")
    _blit_clipped(screen, name_font.render(name, True, MUTED if completed else DIM), x + 92, y + 8, width - 182)
    if completed:
        if pos == 1 or leader_ticks is None:
            text, color = f"{int(client_result['lap_ticks']) / FPS:.3f}", accent
        else:
            text, color = f"+{(int(client_result['lap_ticks']) - leader_ticks) / FPS:.3f}", SILVER
    else:
        text, color = f"{float(client_result['max_progress']):.0f}", DIM
    interval = fonts["row_int"].render(text, True, color)
    screen.blit(interval, (x + width - interval.get_width() - 6, y + 8))


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
    is_final = session.competition_id == "final"
    if not session.leaderboard:
        screen.blit(
            fonts["meta"].render("Waiting for completed submissions", True, MUTED),
            (rect.x + 4, rect.y + 8),
        )
        return
    if not session.leaderboard_revealed:
        _draw_leaderboard_reveal_panel(screen, session, rect, accent, fonts)
        return

    entries = session.leaderboard
    if is_final:
        pod_bottom = _draw_final_podium(screen, rect, entries[:3], fonts)
    else:
        pod_bottom = _draw_phase_one_podium(screen, rect, entries[:3], fonts, session.competition_id)

    leader_ticks = _leader_ticks(entries)
    row_h = 40 if is_final else 30
    y = pod_bottom + 16
    for entry in entries[3 : 3 + rows]:
        _draw_tower_row(screen, rect.x, y, rect.width, entry, fonts, accent, leader_ticks, session.competition_id)
        pygame.draw.line(screen, ROW_LINE, (rect.x, y + row_h - 2), (rect.right, y + row_h - 2), 1)
        y += row_h

    shown = min(len(entries), 3 + rows)
    footer_y = rect.bottom - 18
    screen.blit(fonts["footer"].render(f"SHOWING {shown} OF {len(entries)}", True, MUTED), (rect.x, footer_y))
    right = fonts["footer"].render("TOP 10" if is_final else "TOP 15 REPLAY", True, accent)
    screen.blit(right, (rect.right - right.get_width(), footer_y))

    if session.reveal_highlight_until > now:  # 2s highlight after a new snapshot reveals
        pygame.draw.rect(screen, accent, rect.inflate(10, 10), 3)


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
    live = status == "RUNNING"
    text = "LIVE" if live else status
    label = fonts["chip_label"].render(text, True, WHITE if live else MUTED)
    dot_w = 14 if live else 0
    badge = pygame.Rect(0, 0, dot_w + label.get_width() + 20, 24)
    badge.topright = (rect.right - 10, rect.y + 10)
    pygame.draw.rect(screen, BG_DEEP, badge)
    pygame.draw.rect(screen, accent if live else BORDER, badge, 1)
    ox = badge.x + 10
    if live:
        _draw_pulse_dot(screen, ox, badge.centery, accent, BG_DEEP, 4)
        ox += dot_w
    screen.blit(label, (ox, badge.centery - label.get_height() // 2))


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


FONTS_DIR = FONT_PATH.parent
# F1 display faces downloaded into fonts/ (SIL Open Font License; see fonts/*-OFL.txt).
_F1_FONT_FILES = {
    "black": "SairaCondensed-Black.ttf",       # 900 display / numerals / tags / banners
    "xbold": "SairaCondensed-ExtraBold.ttf",   # 800 stage label / chip value / tower tag
    "bold": "SairaCondensed-Bold.ttf",         # 700 chip label / footer
    "semi": "SairaSemiCondensed-Bold.ttf",     # tabular timing digits (intervals)
    "ti_black": "TitilliumWeb-Black.ttf",      # 900 wordmark / ascii identity
    "ti_bold": "TitilliumWeb-Bold.ttf",        # 700 ascii sub text
}


def _fonts() -> dict[str, pygame.font.Font]:
    def cjk(size: int, *, bold: bool = False) -> pygame.font.Font:
        for path in _font_path_candidates(bold=bold):
            if os.path.exists(path):
                return pygame.font.Font(path, size)
        for name in _font_name_candidates():
            matched = pygame.font.match_font(name, bold=bold)
            if matched:
                return pygame.font.Font(matched, size)
        return pygame.font.SysFont("Arial", size, bold=bold)

    def f1(family: str, size: int) -> pygame.font.Font:
        path = FONTS_DIR / _F1_FONT_FILES[family]
        if path.exists():
            return pygame.font.Font(str(path), size)
        return cjk(size, bold=True)  # graceful fallback if a TTF is missing

    return {
        # --- F1 chrome (ASCII only: wordmark, labels, numerals, tags, results) ---
        "wordmark": f1("ti_black", 25),
        "stage": f1("xbold", 16),
        "chip_label": f1("bold", 13),
        "chip_value": f1("xbold", 19),
        "banner": f1("black", 44),
        "banner_fin": f1("black", 40),
        "pod_tag": f1("black", 21),
        "pod_result": f1("black", 22),
        "pod_ghost": f1("black", 78),
        "pod_ghost_fin": f1("black", 46),
        "pod_name": f1("ti_black", 22),
        "row_pos": f1("black", 16),
        "row_tag": f1("xbold", 15),
        "row_int": f1("semi", 13),
        "footer": f1("bold", 11),
        "car_tag": f1("black", 12),
        # --- user-supplied text (CJK-capable; usernames / groups may be Chinese) ---
        "pod_sub": f1("ti_bold", 13),
        "pod_sub_cjk": cjk(13),
        "row_name": f1("ti_bold", 14),
        "row_name_cjk": cjk(14),
        # --- legacy keys for waiting / reveal / centered screens (CJK-capable) ---
        "title": cjk(28, bold=True),
        "status": cjk(30, bold=True),
        "chip": cjk(20, bold=True),
        "panel": cjk(18, bold=True),
        "row": cjk(17, bold=True),
        "label": cjk(15, bold=True),
        "meta": cjk(14),
    }


def _font_path_candidates(*, bold: bool) -> list[str]:
    configured = os.environ.get("COMPETITION_REPLAY_FONT_PATH")
    candidates = [
        str(FONT_PATH),
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
