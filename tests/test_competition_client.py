from __future__ import annotations

import math
import os

import pygame
import pytest

from game_engine.backend.assets import load_game_assets
from game_engine.backend.car import Car
from game_engine.backend.settings import HIDDEN_LAYER, INPUT_LAYER, OUTPUT_LAYER
from game_engine.backend.training_session import TrainingSession
from game_engine.frontend.competition_client import (
    CompetitionTrainingClient,
    build_manual_client_result,
    evaluate_car_result,
    parse_bool,
)
from game_engine.frontend.submission_client import submit_car
from server.competition_config import FRAME_LIMIT
from server.competition_maps import get_competition_map


LAYER_SIZES = [INPUT_LAYER, HIDDEN_LAYER, OUTPUT_LAYER]


@pytest.fixture
def competition_client():
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    screen = pygame.display.set_mode((1600, 900))
    from shared.contracts import RuntimeSettings

    settings = RuntimeSettings(population_size=4, mutation_rate=0)
    return CompetitionTrainingClient(
        settings=settings,
        assets=load_game_assets(),
        screen=screen,
        clock=pygame.time.Clock(),
        font=pygame.font.SysFont("Arial", 18),
        small_font=pygame.font.SysFont("Arial", 15),
        title_font=pygame.font.SysFont("Arial", 26, bold=True),
        session=TrainingSession.from_settings(settings),
    )


def test_manual_client_result_supports_completed_and_incomplete_results():
    completed = build_manual_client_result(
        completed="true",
        lap_ticks="412",
        max_progress="4380.5",
        ticks_to_max_progress="412",
    )
    incomplete = build_manual_client_result(
        completed="false",
        lap_ticks="",
        max_progress="1250.5",
        ticks_to_max_progress="840",
    )

    assert completed.completed is True
    assert completed.lap_ticks == 412
    assert incomplete.completed is False
    assert incomplete.lap_ticks is None
    assert incomplete.max_progress == 1250.5


def test_manual_client_result_rejects_inconsistent_lap_ticks():
    with pytest.raises(ValueError, match="lap_ticks"):
        build_manual_client_result(
            completed="false",
            lap_ticks="12",
            max_progress="10",
            ticks_to_max_progress="4",
        )


def test_parse_bool_accepts_ui_friendly_values():
    assert parse_bool("completed") is True
    assert parse_bool("yes") is True
    assert parse_bool("incomplete") is False
    assert parse_bool("") is False


def test_generated_client_result_is_test_only_incomplete_result():
    pygame.init()
    car = Car(LAYER_SIZES)
    for layer in car.weights + car.biases:
        layer.fill(0.0)

    result = evaluate_car_result(car, "easy")

    assert result.completed is False
    assert result.lap_ticks is None
    assert math.isfinite(result.max_progress)
    assert result.max_progress >= 0.0
    assert 0 <= result.ticks_to_max_progress <= FRAME_LIMIT


def test_competition_client_maps_have_spawn_and_collision_surface():
    pygame.init()
    for competition_id in ("easy", "hard", "final"):
        competition_map = get_competition_map(competition_id)
        spawn = competition_map.spawn
        collision = competition_map.build_collision_surface()
        pixel = collision.get_at((round(spawn["x"]), round(spawn["y"])))

        assert competition_map.front_path.exists()
        assert pixel.a > 0


def test_submit_client_still_requires_explicit_client_result():
    result = submit_car(
        server_url="http://127.0.0.1:1",
        car=object(),
        group_id="1",
        username="ada",
    )

    assert result.ok is False
    assert "client_result" in result.message
    assert "competition_main.py" in result.message


def test_auto_breed_shortcut_works_even_when_user_field_is_active(competition_client):
    user_field = competition_client.fields[0]
    user_field.active = True
    before_value = user_field.value

    competition_client.handle_event(
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_g, unicode="g")
    )

    assert competition_client.session.generation == 2
    assert user_field.value == before_value
    assert "auto-bred" in competition_client.status


def test_active_field_still_accepts_normal_text(competition_client):
    user_field = competition_client.fields[0]
    user_field.active = True

    competition_client.handle_event(
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_x, unicode="x")
    )

    assert user_field.value.endswith("x")
