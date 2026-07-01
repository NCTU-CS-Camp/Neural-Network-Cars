from __future__ import annotations

import pygame
import pytest

import game_engine.frontend.screens as screens
from game_engine.frontend.screens import (
    _fitness_parameter_lines,
    _simulate_candidates,
    format_timestamp_utc8,
    format_ticks_as_seconds,
)
from shared.contracts import FitnessConfig, LoginProfile


class _FakeCar:
    def __init__(self, *, collided: bool = False) -> None:
        self.center = (0.0, 0.0)
        self._collided = collided
        self.collision_surface: pygame.Surface | None = None

    def set_collision_surface(self, surface: pygame.Surface) -> None:
        self.collision_surface = surface

    def reset_state(
        self,
        x: float,
        y: float,
        angle: float,
        *,
        car_image: pygame.Surface,
    ) -> None:
        del angle, car_image
        self.center = (x, y)

    def update(self) -> None:
        self.center = (self.center[0] + 1.0, self.center[1])

    def collision(self) -> bool:
        return self._collided

    def feedforward(self) -> None:
        return

    def takeAction(self) -> None:
        return

    def draw(self, surface: pygame.Surface) -> None:
        del surface


class _CompletingTracker:
    def __init__(self) -> None:
        self.completed = False
        self.advance_count = 0

    def advance(
        self,
        previous: tuple[float, float],
        current: tuple[float, float],
        *,
        tick: int,
    ) -> None:
        del previous, current, tick
        self.advance_count += 1
        self.completed = True


class _FakeRecord:
    def __init__(self, record_id: str) -> None:
        self.record_id = record_id
        self.record_name = record_id
        self.saved_at = "2026-06-29"
        self.fitness_config = FitnessConfig()
        self.best_fitness_score = None
        self.mlp_init_seed = 3057
        self.max_speed = 10


class _FakeRecordStore:
    def __init__(self) -> None:
        self.records = [_FakeRecord("first"), _FakeRecord("second")]
        self.deleted: list[str] = []

    def list_records(self) -> list[_FakeRecord]:
        return list(self.records)

    def delete_record(self, record_id: str) -> None:
        self.deleted.append(record_id)
        self.records = [
            record for record in self.records if record.record_id != record_id
        ]


def test_login_uses_preconfigured_server_url(monkeypatch) -> None:
    events = [
        pygame.event.Event(
            pygame.MOUSEBUTTONDOWN,
            {"button": 1, "pos": (88, 248)},
        ),
        pygame.event.Event(
            pygame.MOUSEBUTTONDOWN,
            {"button": 1, "pos": (100, 360)},
        ),
        pygame.event.Event(pygame.TEXTEDITING, {"text": "ㄨ"}),
        pygame.event.Event(pygame.TEXTINPUT, {"text": "吳榮恆"}),
        pygame.event.Event(
            pygame.MOUSEBUTTONDOWN,
            {"button": 1, "pos": (100, 450)},
        ),
    ]
    monkeypatch.setattr(pygame.event, "get", lambda: events)
    monkeypatch.setattr(
        screens,
        "save_login_profile",
        lambda _: None,
    )
    pygame.font.init()

    profile = screens.run_login_screen(
        pygame.Surface((1600, 900)),
        "http://192.168.1.20:8000",
    )

    assert profile.group_id == "1"
    assert profile.username == "吳榮恆"
    assert profile.server_url == "http://192.168.1.20:8000"


def test_main_menu_exposes_clear_user_action(monkeypatch) -> None:
    events = [
        pygame.event.Event(
            pygame.MOUSEBUTTONDOWN,
            {"button": 1, "pos": (800, 618)},
        )
    ]
    monkeypatch.setattr(pygame.event, "get", lambda: events)
    pygame.font.init()

    choice = screens.run_main_menu_screen(
        pygame.Surface((1600, 900)),
        LoginProfile(group_id="1", username="apollo"),
    )

    assert choice == "clear_user"


@pytest.mark.parametrize(
    ("position", "expected"),
    [
        ((700, 538), True),
        ((900, 538), False),
    ],
)
def test_clear_user_requires_confirmation(
    monkeypatch,
    position: tuple[int, int],
    expected: bool,
) -> None:
    events = [
        pygame.event.Event(
            pygame.MOUSEBUTTONDOWN,
            {"button": 1, "pos": position},
        )
    ]
    monkeypatch.setattr(pygame.event, "get", lambda: events)
    pygame.font.init()

    assert (
        screens.run_clear_user_confirm_screen(pygame.Surface((1600, 900)))
        is expected
    )


def test_ticks_are_displayed_as_seconds_with_one_decimal() -> None:
    assert format_ticks_as_seconds(45, fps=30) == "1.5 秒"
    assert format_ticks_as_seconds(0, fps=30) == "0.0 秒"
    assert format_ticks_as_seconds(None, fps=30) == "--"


def test_timestamp_is_displayed_in_utc_plus_8() -> None:
    assert format_timestamp_utc8(
        "2026-06-29T03:15:27.171244+00:00"
    ) == "2026-06-29 11:15:27 UTC+8"


def test_all_ten_fitness_parameters_are_split_across_two_lines() -> None:
    config = FitnessConfig(
        crash=70,
        spin=40,
        stall=50,
        time=30,
        wrong_way=0,
        alignment=1,
        centered=2,
        progress=60,
        safety=3,
        speed=40,
    )

    penalty_line, reward_line = _fitness_parameter_lines(config)

    assert penalty_line == (
        "Penalties  crash:70  spin:40  stall:50  time:30  wrong_way:0"
    )
    assert reward_line == (
        "Rewards    alignment:1  centered:2  progress:60  safety:3  speed:40"
    )


def test_validation_stops_after_first_clean_completion(monkeypatch) -> None:
    configured_speeds: list[int] = []
    monkeypatch.setattr(pygame.event, "get", lambda: [])
    monkeypatch.setattr(pygame.display, "update", lambda: None)
    monkeypatch.setattr(
        screens,
        "configure_car",
        lambda track_back, car_image, max_speed: configured_speeds.append(
            max_speed
        ),
    )
    monkeypatch.setattr(
        screens,
        "_font",
        lambda size=22: pygame.font.Font(None, size),
    )
    pygame.font.init()

    cars = [_FakeCar(), _FakeCar()]
    stale_surface = pygame.Surface((10, 10))
    for car in cars:
        car.collision_surface = stale_surface
    trackers = [_CompletingTracker(), _CompletingTracker()]
    surface = pygame.Surface((100, 100))

    survival = _simulate_candidates(
        surface,
        surface,
        surface,
        {"x": 0.0, "y": 0.0, "angle": 180.0},
        cars,
        surface,
        frame_limit=10,
        trackers=trackers,
        title="Validation",
        stop_on_first_completion=True,
        max_speed=25,
    )

    assert survival == [1, 1]
    assert [tracker.advance_count for tracker in trackers] == [1, 1]
    assert configured_speeds == [25]
    assert all(car.collision_surface is surface for car in cars)


def test_collision_frame_does_not_count_as_valid_completion(monkeypatch) -> None:
    monkeypatch.setattr(pygame.event, "get", lambda: [])
    monkeypatch.setattr(pygame.display, "update", lambda: None)
    monkeypatch.setattr(
        screens,
        "_font",
        lambda size=22: pygame.font.Font(None, size),
    )
    pygame.font.init()

    tracker = _CompletingTracker()
    surface = pygame.Surface((100, 100))

    survival = _simulate_candidates(
        surface,
        surface,
        surface,
        {"x": 0.0, "y": 0.0, "angle": 180.0},
        [_FakeCar(collided=True)],
        surface,
        frame_limit=10,
        trackers=[tracker],
        title="Validation",
        stop_on_first_completion=True,
    )

    assert survival == [1]
    assert not tracker.completed
    assert tracker.advance_count == 0


@pytest.mark.parametrize(
    ("release_position", "expected_deleted"),
    [
        ((1475, 190), ["first"]),
        ((1475, 326), []),
    ],
)
def test_delete_requires_release_on_same_record(
    monkeypatch,
    release_position: tuple[int, int],
    expected_deleted: list[str],
) -> None:
    store = _FakeRecordStore()
    events = [
        pygame.event.Event(
            pygame.MOUSEBUTTONDOWN,
            {"button": 1, "pos": (1475, 190)},
        ),
        pygame.event.Event(
            pygame.MOUSEMOTION,
            {"pos": release_position, "buttons": (1, 0, 0)},
        ),
        pygame.event.Event(
            pygame.MOUSEBUTTONUP,
            {"button": 1, "pos": release_position},
        ),
        pygame.event.Event(pygame.QUIT),
    ]
    monkeypatch.setattr(screens, "RecordStore", lambda: store)
    monkeypatch.setattr(pygame.event, "get", lambda: events)
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (0, 0))

    with pytest.raises(screens.AppQuit):
        screens.run_validation_list_screen(
            pygame.Surface((1600, 900)),
            "http://127.0.0.1:8000",
        )

    assert store.deleted == expected_deleted
