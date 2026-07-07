from __future__ import annotations

import math
import os

import pygame
import pytest

import game_engine.frontend.competition_client as client_module
from game_engine.backend.assets import load_game_assets
from game_engine.backend.car import Car, configure_car
from game_engine.backend.settings import HIDDEN_LAYER, INPUT_LAYER, OUTPUT_LAYER
from game_engine.backend.training_session import TrainingSession
from game_engine.frontend.competition_client import (
    AuthenticatedSession,
    CompetitionTrainingClient,
    NetworkError,
    authenticate_user,
    build_manual_client_result,
    check_eligibility,
    evaluate_car_result,
    parse_bool,
    update_user_nickname,
)
from game_engine.frontend.submission_client import submit_car
from server.competition_config import FRAME_LIMIT
from server.competition_maps import get_competition_map
from shared.contracts import ClientResult, RuntimeSettings, SubmissionPayload


LAYER_SIZES = [INPUT_LAYER, HIDDEN_LAYER, OUTPUT_LAYER]


@pytest.fixture
def competition_client():
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    screen = pygame.display.set_mode((1600, 900))

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
        max_progress="100.0",
        ticks_to_max_progress="412",
    )
    incomplete = build_manual_client_result(
        completed="false",
        lap_ticks="",
        max_progress="28.5",
        ticks_to_max_progress="840",
    )

    assert completed.completed is True
    assert completed.lap_ticks == 412
    assert incomplete.completed is False
    assert incomplete.lap_ticks is None
    assert incomplete.max_progress == 28.5


def test_manual_client_result_rejects_inconsistent_lap_ticks():
    with pytest.raises(ValueError, match="lap_ticks"):
        build_manual_client_result(
            completed="false",
            lap_ticks="12",
            max_progress="10",
            ticks_to_max_progress="4",
        )


def test_client_result_converts_pixel_progress_to_api_percentage():
    result = ClientResult(
        completed=False,
        lap_ticks=None,
        max_progress=989.0322580645161,
        ticks_to_max_progress=98,
    )

    converted = result.as_progress_percentage(4_000.0)

    assert converted.max_progress == 24.725806
    assert converted.ticks_to_max_progress == 98


def test_parse_bool_accepts_ui_friendly_values():
    assert parse_bool("completed") is True
    assert parse_bool("yes") is True
    assert parse_bool("incomplete") is False
    assert parse_bool("") is False


def test_competition_client_uses_settings_server_url(competition_client):
    competition_client.fields[2].value = "student-password"
    competition_client.fields[5].value = "http://192.168.1.20:8000/"

    assert competition_client.server_url == "http://192.168.1.20:8000"


def test_competition_client_does_not_override_settings_url_from_environment(
    monkeypatch,
):
    monkeypatch.setenv("COMPETITION_SERVER_URL", "http://env.example:8000")
    settings = RuntimeSettings(server_url="http://settings.example:8000")

    fields = client_module._build_fields(settings)

    assert fields[5].value == "http://settings.example:8000"


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
    assert result.max_progress <= 100.0
    assert 0 <= result.ticks_to_max_progress <= FRAME_LIMIT


def test_generated_client_result_does_not_clear_global_car_sprite():
    pygame.init()
    assets = load_game_assets()
    collision = get_competition_map("easy").build_collision_surface()
    configure_car(collision, assets.white_small_car, 10)
    car = Car(LAYER_SIZES)

    evaluate_car_result(car, "easy", max_speed=12.5)

    assert Car(LAYER_SIZES).car_image is assets.white_small_car


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
    assert "本機評測結果" in result.message
    assert "competition_main.py" in result.message


def test_authenticate_user_returns_bearer_session(monkeypatch) -> None:
    monkeypatch.setattr(
        client_module,
        "_post_json",
        lambda *args, **kwargs: (
            200,
            {
                "token": "student-token",
                "expires_at": "2026-07-03T14:00:00+00:00",
                "group_id": "1",
                "username": "ada",
                "nickname": "Ada Lovelace",
            },
        ),
    )

    result = authenticate_user(
        "http://localhost:8000",
        group_id="1",
        username="ada",
        password="pw",
    )

    assert isinstance(result, AuthenticatedSession)
    assert result.token == "student-token"
    assert result.nickname == "Ada Lovelace"


def test_authenticate_user_reports_invalid_credentials(monkeypatch) -> None:
    monkeypatch.setattr(
        client_module,
        "_post_json",
        lambda *args, **kwargs: (401, {"detail": "invalid credentials"}),
    )

    result = authenticate_user(
        "http://localhost:8000",
        group_id="1",
        username="ada",
        password="wrong",
    )

    assert isinstance(result, NetworkError)
    assert "401" in result.message


def test_update_user_nickname_uses_bearer_profile_api(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_patch_json(url, payload, timeout=10.0, token=None):
        captured.update(url=url, payload=payload, timeout=timeout, token=token)
        return 200, {"nickname": "Ada Driver"}

    monkeypatch.setattr(client_module, "_patch_json", fake_patch_json)

    result = update_user_nickname(
        "http://localhost:8000/",
        token="student-token",
        nickname="Ada Driver",
    )

    assert result == "Ada Driver"
    assert captured == {
        "url": "http://localhost:8000/v2/me",
        "payload": {"nickname": "Ada Driver"},
        "timeout": 10.0,
        "token": "student-token",
    }


def test_eligibility_forwards_bearer_token(monkeypatch) -> None:
    captured: dict[str, str | None] = {}

    def fake_post_json(url, payload, timeout=10.0, token=None):
        del url, payload, timeout
        captured["token"] = token
        return (
            200,
            {
                "eligible": True,
                "reason": None,
                "stage": "phase_one",
                "next_submission_at": "2026-07-03T02:00:00+00:00",
                "competition_config_version": "competition-2026-v1",
            },
        )

    monkeypatch.setattr(client_module, "_post_json", fake_post_json)

    result = check_eligibility(
        "http://localhost:8000",
        "easy",
        "1",
        "ada",
        token="student-token",
    )

    assert not isinstance(result, NetworkError)
    assert result.eligible
    assert captured["token"] == "student-token"


def test_submission_forwards_bearer_token_without_logging_payload(
    monkeypatch,
    capsys,
) -> None:
    captured: dict[str, object] = {}

    def fake_post_json(url, payload, timeout=10.0, token=None):
        del url, timeout
        captured["payload"] = payload
        captured["token"] = token
        return (201, {"submission_id": "sub_1", "status": "queued"})

    monkeypatch.setattr(client_module, "_post_json", fake_post_json)
    payload = SubmissionPayload(
        group_id="1",
        username="ada",
        weights=[[0.0] * 36, [0.0] * 24],
        biases=[[0.0] * 6, [0.0] * 4],
    )
    client_result = ClientResult(
        completed=False,
        lap_ticks=None,
        max_progress=100.0,
        ticks_to_max_progress=20,
    )

    result = client_module.submit(
        "http://localhost:8000",
        "easy",
        payload,
        client_result,
        token="student-token",
    )

    assert isinstance(result, client_module.SubmissionAccepted)
    assert captured["token"] == "student-token"
    assert captured["payload"] == {
        "group_id": "1",
        "username": "ada",
        "skin_id": 0,
        "maxSpeed": 10.0,
        "weights": [[0.0] * 36, [0.0] * 24],
        "biases": [[0.0] * 6, [0.0] * 4],
        "client_result": {
            "completed": False,
            "lap_ticks": None,
            "max_progress": 100.0,
            "ticks_to_max_progress": 20,
        },
    }
    terminal_output = capsys.readouterr().out
    assert "Competition submission payload:" not in terminal_output
    assert '"username": "ada"' not in terminal_output


def test_auto_breed_shortcut_works_even_when_user_field_is_active(competition_client):
    user_field = competition_client.fields[0]
    user_field.active = True
    before_value = user_field.value

    competition_client.handle_event(
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_g, unicode="g")
    )

    assert competition_client.session.generation == 2
    assert user_field.value == before_value
    assert "自動繁殖" in competition_client.status


def test_active_field_still_accepts_normal_text(competition_client):
    user_field = competition_client.fields[0]
    user_field.active = True

    competition_client.handle_event(
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_x, unicode="x")
    )

    assert user_field.value.endswith("x")
