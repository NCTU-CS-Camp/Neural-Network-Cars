from __future__ import annotations

import pygame
import pytest

import game_engine.frontend.screens as screens
from game_engine.frontend.screens import (
    _simulate_candidates,
    format_ticks_as_seconds,
)
from shared.contracts import FitnessConfig


class _FakeCar:
    def __init__(self, *, collided: bool = False) -> None:
        self.center = (0.0, 0.0)
        self._collided = collided

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


def test_ticks_are_displayed_as_seconds_with_one_decimal() -> None:
    assert format_ticks_as_seconds(45, fps=30) == "1.5 秒"
    assert format_ticks_as_seconds(0, fps=30) == "0.0 秒"
    assert format_ticks_as_seconds(None, fps=30) == "--"


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
        ((1475, 150), ["first"]),
        ((1475, 214), []),
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
            {"button": 1, "pos": (1475, 150)},
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
