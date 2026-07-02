from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

import pygame
from fastapi.testclient import TestClient

from server.app import create_app
from server.competition_config import STAGNATION_TICKS
from server.competition_maps import get_competition_map
from server.evaluation_worker import BatchWorker
from server.storage import CompetitionStorage
from shared.contracts import ALLOWED_SKIN_IDS


class Clock:
    def __init__(self) -> None:
        self.current = datetime(2026, 6, 26, 10, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, **kwargs: int) -> None:
        self.current += timedelta(**kwargs)


def make_payload(
    *,
    group_id: str = "1",
    username: str = "tester",
    completed: bool = False,
    lap_ticks: int | None = None,
    max_progress: float = 1_000.0,
    ticks_to_max_progress: int = 300,
) -> dict:
    if completed and lap_ticks is None:
        lap_ticks = 500
    return {
        "group_id": group_id,
        "username": username,
        "weights": [[0.0] * 36, [0.0] * 24],
        "biases": [[0.0] * 6, [0.0] * 4],
        "client_result": {
            "completed": completed,
            "lap_ticks": lap_ticks,
            "max_progress": max_progress,
            "ticks_to_max_progress": ticks_to_max_progress,
        },
    }


def make_client(tmp_path, clock: Clock) -> TestClient:
    storage = CompetitionStorage(tmp_path / "competition.db", clock=clock)
    return TestClient(create_app(storage=storage, start_worker=False, admin_token="secret"))


def create_user(
    client: TestClient,
    *,
    group_id: str = "1",
    username: str = "tester",
    password: str = "pw",
    disabled: bool = False,
) -> dict:
    response = client.post(
        "/v2/admin/users",
        headers={"X-Admin-Token": "secret"},
        json={
            "group_id": group_id,
            "username": username,
            "password": password,
            "disabled": disabled,
        },
    )
    assert response.status_code == 200
    return response.json()


def auth_headers(
    client: TestClient,
    *,
    group_id: str = "1",
    username: str = "tester",
    password: str = "pw",
) -> dict[str, str]:
    create_user(client, group_id=group_id, username=username, password=password)
    response = client.post(
        "/v2/auth/login",
        json={"group_id": group_id, "username": username, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


def student_post(client: TestClient, path: str, payload: dict) -> Any:
    headers = auth_headers(
        client,
        group_id=str(payload.get("group_id", "1")),
        username=str(payload.get("username", "tester")),
    )
    return client.post(path, json=payload, headers=headers)


def submit(client: TestClient, competition_id: str, **kwargs) -> dict:
    payload = make_payload(**kwargs)
    response = client.post(
        f"/v2/competitions/{competition_id}/submissions",
        json=payload,
        headers=auth_headers(
            client,
            group_id=payload["group_id"],
            username=payload["username"],
        ),
    )
    assert response.status_code == 201
    return response.json()


def process_now(client: TestClient) -> int:
    response = client.post(
        "/v2/admin/batches/run-now",
        headers={"X-Admin-Token": "secret"},
    )
    assert response.status_code == 200
    return int(response.json()["processed"])


def test_batch_worker_retries_after_transient_failure(caplog):
    recovered = threading.Event()

    class FlakyStorage:
        calls = 0

        def seal_due_batches(self, *, now=None, force=False):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary database failure")
            recovered.set()
            return 0

    storage = FlakyStorage()
    worker = BatchWorker(storage, poll_interval=0.01)  # type: ignore[arg-type]

    worker.start()
    try:
        assert recovered.wait(timeout=1.0)
    finally:
        worker.stop()

    assert storage.calls >= 2
    assert "Snapshot batch processing failed; retrying after poll interval" in caplog.text


def test_phase_one_submission_is_queued_and_cooldown_is_per_competition(tmp_path):
    clock = Clock()
    with make_client(tmp_path, clock) as client:
        headers = auth_headers(client, username="ada")
        eligibility = client.post(
            "/v2/competitions/easy/eligibility",
            json={"group_id": "1", "username": "ada"},
            headers=headers,
        )
        first = submit(client, "easy", username="ada")
        easy_again = client.post(
            "/v2/competitions/easy/eligibility",
            json={"group_id": "1", "username": "ada"},
            headers=headers,
        )
        hard = client.post(
            "/v2/competitions/hard/eligibility",
            json={"group_id": "1", "username": "ada"},
            headers=headers,
        )
        duplicate = client.post(
            "/v2/competitions/easy/submissions",
            json=make_payload(username="ada"),
            headers=headers,
        )

    assert eligibility.json()["eligible"] is True
    assert first["status"] == "queued"
    assert easy_again.json()["reason"] == "submission_cooldown"
    assert hard.json()["eligible"] is True
    assert duplicate.status_code == 429
    assert duplicate.json()["error"] == "submission_cooldown"


def test_default_phase_one_interval_is_one_minute_and_admin_can_update(tmp_path):
    clock = Clock()
    with make_client(tmp_path, clock) as client:
        initial = client.get("/v2/state").json()
        updated = client.post(
            "/v2/admin/config",
            headers={"X-Admin-Token": "secret"},
            json={"phase_one_batch_minutes": 2},
        )
        renamed = client.post(
            "/v2/admin/config",
            headers={"X-Admin-Token": "secret"},
            json={"snapshot_interval_minutes": 5},
        )
        invalid = client.post(
            "/v2/admin/config",
            headers={"X-Admin-Token": "secret"},
            json={"phase_one_batch_minutes": 3},
        )

    assert initial["config"]["phase_one_batch_minutes"] == 1
    assert initial["config"]["snapshot_interval_minutes"] == 1
    assert initial["config"]["next_phase_one_batch_at"].endswith("10:02:00+00:00")
    assert initial["config"]["next_snapshot_at"].endswith("10:02:00+00:00")
    assert updated.status_code == 200
    assert updated.json()["config"]["phase_one_batch_minutes"] == 2
    assert updated.json()["config"]["snapshot_interval_minutes"] == 2
    assert updated.json()["config"]["next_phase_one_batch_at"].endswith("10:02:00+00:00")
    assert updated.json()["config"]["next_snapshot_at"].endswith("10:02:00+00:00")
    assert renamed.status_code == 200
    assert renamed.json()["config"]["snapshot_interval_minutes"] == 5
    assert renamed.json()["config"]["next_snapshot_at"].endswith("10:05:00+00:00")
    assert invalid.status_code == 400
    assert "phase_one_batch_minutes" in invalid.json()["detail"]


def test_admin_state_requires_token_and_public_state_remains_public(tmp_path):
    clock = Clock()
    with make_client(tmp_path, clock) as client:
        public_state = client.get("/v2/state")
        missing_token = client.get("/v2/admin/state")
        bad_token = client.get("/v2/admin/state", headers={"X-Admin-Token": "wrong"})
        admin_state = client.get("/v2/admin/state", headers={"X-Admin-Token": "secret"})

    assert public_state.status_code == 200
    assert missing_token.status_code == 401
    assert bad_token.status_code == 401
    assert admin_state.status_code == 200
    assert admin_state.json() == public_state.json()


def test_admin_page_gates_content_behind_session_token(tmp_path):
    clock = Clock()
    with make_client(tmp_path, clock) as client:
        response = client.get("/admin")

    html = response.text
    assert response.status_code == 200
    assert '/v2/admin/state' in html
    assert '/v2/state' not in html
    assert 'sessionStorage' in html
    assert 'Phase 1 Timing' not in html
    assert 'Snapshot Timing' in html
    assert 'User Management' in html
    assert '/v2/admin/users' in html
    assert '/v2/admin/submissions' in html
    assert 'data-action="enable"' in html
    assert 'id="admin-content" class="hidden"' in html


def test_user_login_authentication_and_expiration(tmp_path):
    clock = Clock()
    with make_client(tmp_path, clock) as client:
        create_user(client, group_id="8", username="ada", password="pw8")
        ok = client.post(
            "/v2/auth/login",
            json={"group_id": "8", "username": "ada", "password": "pw8"},
        )
        bad_password = client.post(
            "/v2/auth/login",
            json={"group_id": "8", "username": "ada", "password": "bad"},
        )
        create_user(
            client,
            group_id="8",
            username="disabled",
            password="pw",
            disabled=True,
        )
        disabled = client.post(
            "/v2/auth/login",
            json={"group_id": "8", "username": "disabled", "password": "pw"},
        )
        token = ok.json()["token"]
        clock.advance(hours=13)
        expired = client.get(
            "/v2/me/submissions",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert ok.status_code == 200
    assert ok.json()["group_id"] == "8"
    assert bad_password.status_code == 401
    assert disabled.status_code == 401
    assert expired.status_code == 401


def test_student_endpoints_require_matching_bearer_identity(tmp_path):
    clock = Clock()
    with make_client(tmp_path, clock) as client:
        missing = client.post(
            "/v2/competitions/easy/eligibility",
            json={"group_id": "1", "username": "ada"},
        )
        mismatch = client.post(
            "/v2/competitions/easy/eligibility",
            json={"group_id": "1", "username": "ben"},
            headers=auth_headers(client, group_id="1", username="ada"),
        )

    assert missing.status_code == 401
    assert mismatch.status_code == 403


def test_admin_can_import_users_and_plaintext_passwords_are_visible(tmp_path):
    clock = Clock()
    with make_client(tmp_path, clock) as client:
        imported = client.post(
            "/v2/admin/users/import",
            headers={"X-Admin-Token": "secret"},
            json={"text": "2,bob,pw2\n3,cy,pw3,true"},
        )
        users = client.get(
            "/v2/admin/users",
            headers={"X-Admin-Token": "secret"},
        )
        invalid_json = client.post(
            "/v2/admin/users/import",
            headers={"X-Admin-Token": "secret"},
            json={"text": "[bad"},
        )

    assert imported.status_code == 200
    assert imported.json()["imported"] == 2
    assert [user["username"] for user in users.json()] == ["bob", "cy"]
    assert users.json()[0]["password_plaintext"] == "pw2"
    assert users.json()[1]["disabled"] is True
    assert invalid_json.status_code == 400
    assert "JSON import text is invalid" in invalid_json.json()["detail"]


def test_phase_one_configured_interval_controls_cooldown(tmp_path):
    clock = Clock()
    with make_client(tmp_path, clock) as client:
        client.post(
            "/v2/admin/config",
            headers={"X-Admin-Token": "secret"},
            json={"phase_one_batch_minutes": 2},
        )
        submit(client, "easy", username="ada")
        clock.advance(minutes=1)
        headers = auth_headers(client, username="ada")
        blocked = client.post(
            "/v2/competitions/easy/submissions",
            json=make_payload(username="ada"),
            headers=headers,
        )
        clock.advance(minutes=1)
        accepted = client.post(
            "/v2/competitions/easy/submissions",
            json=make_payload(username="ada"),
            headers=headers,
        )

    assert blocked.status_code == 429
    assert blocked.json()["error"] == "submission_cooldown"
    assert accepted.status_code == 201


def test_batch_boundary_seals_queued_submissions_and_persists_snapshot(tmp_path):
    clock = Clock()
    storage = CompetitionStorage(tmp_path / "competition.db", clock=clock)
    from shared.contracts import ClientResult, SubmissionPayload

    storage.set_phase_one_batch_minutes(2)
    payload = SubmissionPayload("1", "ada", [[0.0] * 36, [0.0] * 24], [[0.0] * 6, [0.0] * 4])
    storage.create_submission("easy", payload, ClientResult(False, None, 1_200.0, 300))

    assert storage.seal_phase_one_batches(now=clock.current) == 0
    clock.advance(minutes=1)
    assert storage.seal_phase_one_batches(now=clock.current) == 1
    leaderboard = storage.leaderboard("easy")
    snapshot = storage.latest_snapshot("easy")

    assert leaderboard[0]["status"] == "completed"
    assert snapshot is not None
    assert snapshot["snapshot"]["submission_ids"] == [leaderboard[0]["submission_id"]]
    assert snapshot["window_start"].endswith("10:00:00+00:00")
    assert snapshot["window_end"].endswith("10:02:00+00:00")


def test_ranking_uses_client_result_and_keeps_individual_historical_best(tmp_path):
    clock = Clock()
    with make_client(tmp_path, clock) as client:
        first = submit(client, "easy", username="ada", max_progress=2_000.0)
        submit(client, "easy", group_id="2", username="ada", completed=True, lap_ticks=520)
        submit(client, "easy", group_id="3", username="ben", completed=True, lap_ticks=480)
        assert process_now(client) == 3

        clock.advance(minutes=5)
        better = submit(client, "easy", username="ada", completed=True, lap_ticks=510)
        assert process_now(client) == 1
        leaderboard = client.get("/v2/competitions/easy/leaderboard").json()

    assert [row["username"] for row in leaderboard] == ["ben", "ada", "ada"]
    assert leaderboard[1]["submission_id"] == better["submission_id"]
    assert first["submission_id"] not in [row["submission_id"] for row in leaderboard]
    assert leaderboard[2]["group_id"] == "2"


def test_submission_metadata_defaults_aliases_and_validation(tmp_path):
    clock = Clock()
    with make_client(tmp_path, clock) as client:
        defaulted = submit(client, "easy", username="defaulted")

        alias_payload = make_payload(username="alias")
        alias_payload["skin_id"] = 3
        alias_payload["maxSpeed"] = 12.5
        alias_response = client.post(
            "/v2/competitions/easy/submissions",
            json=alias_payload,
            headers=auth_headers(client, username="alias"),
        )

        bad_skin = make_payload(username="badskin")
        bad_skin["skin_id"] = 99
        bad_skin_response = client.post(
            "/v2/competitions/easy/submissions",
            json=bad_skin,
            headers=auth_headers(client, username="badskin"),
        )

        bad_speed = make_payload(username="badspeed")
        bad_speed["max_speed"] = 99
        bad_speed_response = client.post(
            "/v2/competitions/easy/submissions",
            json=bad_speed,
            headers=auth_headers(client, username="badspeed"),
        )
        process_now(client)
        leaderboard = client.get("/v2/competitions/easy/leaderboard").json()
        replay = client.get(
            "/v2/admin/replay",
            headers={"X-Admin-Token": "secret"},
        ).json()

    assert defaulted["skin_id"] == 0
    assert defaulted["max_speed"] == 10.0
    assert alias_response.status_code == 201
    assert alias_response.json()["skin_id"] == 3
    assert alias_response.json()["max_speed"] == 12.5
    assert bad_skin_response.status_code == 400
    assert "skin_id" in bad_skin_response.json()["detail"]
    assert bad_speed_response.status_code == 400
    assert "max_speed" in bad_speed_response.json()["detail"]
    assert {row["username"]: row["skin_id"] for row in leaderboard}["alias"] == 3
    assert {item["username"]: item["max_speed"] for item in replay["replays"]["easy"]["items"]}[
        "alias"
    ] == 12.5


def test_submission_skin_ids_match_shop_catalog():
    from game_engine.frontend.shop.catalog import all_skins

    assert set(ALLOWED_SKIN_IDS) == {skin.id for skin in all_skins()}


def test_server_logs_received_submission_payload_without_token(tmp_path, capsys):
    clock = Clock()
    with make_client(tmp_path, clock) as client:
        payload = make_payload(group_id="8", username="玩家一號")
        payload["skin_id"] = 3
        payload["maxSpeed"] = 10.0
        response = client.post(
            "/v2/competitions/easy/submissions",
            json=payload,
            headers=auth_headers(client, group_id="8", username="玩家一號"),
        )

    output = capsys.readouterr().out
    assert response.status_code == 201
    assert "Received competition submission payload:" in output
    assert '"username": "玩家一號"' in output
    assert '"skin_id": 3' in output
    assert '"maxSpeed": 10.0' in output
    assert '"lap_ticks": null' in output
    assert "Bearer " not in output


def test_admin_soft_delete_removes_submission_and_recomputes_best(tmp_path):
    clock = Clock()
    with make_client(tmp_path, clock) as client:
        first = submit(client, "easy", username="ada", max_progress=2_000.0)
        process_now(client)
        clock.advance(minutes=1)
        second = submit(client, "easy", username="ada", max_progress=1_000.0)
        process_now(client)

        deleted = client.delete(
            f"/v2/admin/submissions/{first['submission_id']}",
            headers={"X-Admin-Token": "secret"},
        )
        leaderboard = client.get("/v2/competitions/easy/leaderboard").json()
        replay = client.get(
            "/v2/admin/replay",
            headers={"X-Admin-Token": "secret"},
        ).json()

    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"
    assert leaderboard[0]["submission_id"] == second["submission_id"]
    assert first["submission_id"] not in [
        item["submission_id"] for item in replay["replays"]["easy"]["items"]
    ]


def test_chinese_username_round_trips_through_leaderboard(tmp_path):
    clock = Clock()
    with make_client(tmp_path, clock) as client:
        submit(client, "easy", username="吳榮恆")
        assert process_now(client) == 1
        leaderboard = client.get("/v2/competitions/easy/leaderboard").json()

    assert leaderboard[0]["username"] == "吳榮恆"


def test_ranking_prefers_completion_then_lap_ticks_then_progress_then_time(tmp_path):
    clock = Clock()
    with make_client(tmp_path, clock) as client:
        submit(client, "hard", username="slow_finish", completed=True, lap_ticks=600)
        submit(client, "hard", username="fast_finish", completed=True, lap_ticks=500)
        submit(client, "hard", username="far", max_progress=3_000.0, ticks_to_max_progress=400)
        submit(client, "hard", username="near", max_progress=2_000.0, ticks_to_max_progress=100)
        process_now(client)
        leaderboard = client.get("/v2/competitions/hard/leaderboard").json()

    assert [row["username"] for row in leaderboard] == [
        "fast_finish",
        "slow_finish",
        "far",
        "near",
    ]


def test_final_stage_queues_submissions_and_uses_group_cooldown(tmp_path):
    clock = Clock()
    with make_client(tmp_path, clock) as client:
        ada_headers = auth_headers(client, group_id="1", username="ada")
        ben_headers = auth_headers(client, group_id="1", username="ben")
        cy_headers = auth_headers(client, group_id="2", username="cy")
        closed = client.post(
            "/v2/finals/submissions",
            json=make_payload(group_id="1", username="ada"),
            headers=ada_headers,
        )
        stage = client.post(
            "/v2/admin/stage",
            headers={"X-Admin-Token": "secret"},
            json={"stage": "final"},
        )
        first = client.post(
            "/v2/finals/submissions",
            json=make_payload(group_id="1", username="ada", completed=True, lap_ticks=520),
            headers=ada_headers,
        )
        cooldown = client.post(
            "/v2/finals/submissions",
            json=make_payload(group_id="1", username="ben", completed=True, lap_ticks=400),
            headers=ben_headers,
        )
        other = client.post(
            "/v2/finals/submissions",
            json=make_payload(group_id="2", username="cy", completed=True, lap_ticks=480),
            headers=cy_headers,
        )
        queued_leaderboard = client.get("/v2/competitions/final/leaderboard").json()
        processed = process_now(client)
        first_leaderboard = client.get("/v2/competitions/final/leaderboard").json()

        clock.advance(minutes=1)
        better = client.post(
            "/v2/finals/submissions",
            json=make_payload(group_id="1", username="ben", completed=True, lap_ticks=400),
            headers=ben_headers,
        )
        processed_better = process_now(client)
        leaderboard = client.get("/v2/competitions/final/leaderboard").json()

    assert closed.status_code == 409
    assert stage.json()["stage"] == "final"
    assert first.status_code == 201
    assert first.json()["status"] == "queued"
    assert first.json()["next_submission_at"].endswith("10:02:00+00:00")
    assert cooldown.status_code == 429
    assert cooldown.json()["error"] == "submission_cooldown"
    assert other.status_code == 201
    assert queued_leaderboard == []
    assert processed == 2
    assert [row["group_id"] for row in first_leaderboard] == ["2", "1"]
    assert better.status_code == 201
    assert better.json()["status"] == "queued"
    assert processed_better == 1
    assert [row["group_id"] for row in leaderboard] == ["1", "2"]
    assert leaderboard[0]["submission_id"] == better.json()["submission_id"]


def test_final_eligibility_keeps_current_group_and_username_schema(tmp_path):
    clock = Clock()
    with make_client(tmp_path, clock) as client:
        client.post(
            "/v2/admin/stage",
            headers={"X-Admin-Token": "secret"},
            json={"stage": "final"},
        )
        eligibility = client.post(
            "/v2/finals/eligibility",
            json={"group_id": "1", "username": "ada"},
            headers=auth_headers(client, group_id="1", username="ada"),
        )

    assert eligibility.status_code == 200
    assert eligibility.json()["eligible"] is True


def test_submission_validation_rejects_bad_client_result_shape_and_non_finite_genes(tmp_path):
    clock = Clock()
    with make_client(tmp_path, clock) as client:
        headers = auth_headers(client)
        bad_result = make_payload(lap_ticks=20)
        bad_result["client_result"]["lap_ticks"] = 20
        result_response = client.post(
            "/v2/competitions/easy/submissions",
            json=bad_result,
            headers=headers,
        )

        bad_shape = make_payload()
        bad_shape["weights"][0] = [0.0]
        shape_response = client.post(
            "/v2/competitions/easy/submissions",
            json=bad_shape,
            headers=headers,
        )

        non_finite = make_payload()
        non_finite["weights"][0][0] = float("nan")
        finite_response = client.post(
            "/v2/competitions/easy/submissions",
            content=json.dumps(non_finite),
            headers={"Content-Type": "application/json", **headers},
        )

    assert result_response.status_code == 400
    assert "lap_ticks" in result_response.json()["detail"]
    assert shape_response.status_code == 400
    assert "weights[0]" in shape_response.json()["detail"]
    assert finite_response.status_code == 400
    assert "finite" in finite_response.json()["detail"]


def test_public_endpoints_do_not_expose_models_and_protected_replay_returns_top_15(tmp_path):
    clock = Clock()
    with make_client(tmp_path, clock) as client:
        for index in range(16):
            submit(
                client,
                "easy",
                group_id=str(index + 1),
                username=f"player{index}",
                max_progress=float(index),
            )
        process_now(client)
        public_submission = client.get(
            "/v2/competitions/easy/submissions/" + client.get("/v2/competitions/easy/leaderboard").json()[0]["submission_id"]
        )
        denied_replay = client.get("/v2/admin/replay")
        replay = client.get("/v2/admin/replay", headers={"X-Admin-Token": "secret"})

    assert "weights" not in public_submission.json()
    assert "biases" not in public_submission.json()
    assert denied_replay.status_code == 401
    assert replay.status_code == 200
    assert len(replay.json()["replays"]["easy"]["items"]) == 15
    assert len(replay.json()["replays"]["easy"]["items"][0]["weights"][0]) == 36


def test_maps_are_fixed_and_collision_surfaces_have_a_drivable_spawn(tmp_path):
    clock = Clock()
    with make_client(tmp_path, clock) as client:
        maps = client.get("/v2/maps").json()
        previews = [client.get(f"/v2/maps/{item['competition_id']}/preview") for item in maps]

    assert [item["map_id"] for item in maps] == [
        "kaggle_easy",
        "kaggle_hard",
        "kaggle_final",
    ]
    assert all(response.status_code == 200 and response.content.startswith(b"\x89PNG") for response in previews)
    pygame.init()
    for competition_id in ("easy", "hard", "final"):
        competition_map = get_competition_map(competition_id)
        spawn = competition_map.spawn
        collision = competition_map.build_collision_surface()
        assert collision.get_at((round(spawn["x"]), round(spawn["y"]))).a > 0


def test_competition_collision_surfaces_use_authored_back_png_alpha():
    pygame.init()
    for competition_id in ("easy", "hard", "final"):
        competition_map = get_competition_map(competition_id)
        collision = competition_map.build_collision_surface()
        authored_back = pygame.image.load(competition_map.back_path)
        collision_mask = pygame.mask.from_surface(collision, threshold=1)
        authored_mask = pygame.mask.from_surface(authored_back, threshold=1)

        assert collision.get_size() == authored_back.get_size()
        assert collision_mask.count() == authored_mask.count()
        assert collision_mask.overlap_area(authored_mask, (0, 0)) == authored_mask.count()


def test_dual_replay_sessions_keep_collision_surfaces_per_car():
    from game_engine.backend.assets import load_game_assets
    from game_engine.frontend.replay_client import load_replay_sessions

    pygame.init()
    pygame.display.set_mode((1, 1))
    item = {
        "rank": 1,
        "submission_id": "sub_demo",
        "group_id": "1",
        "username": "ada",
        "client_result": make_payload()["client_result"],
        "weights": [[0.0] * 36, [0.0] * 24],
        "biases": [[0.0] * 6, [0.0] * 4],
    }
    sessions = load_replay_sessions(
        {
            "replays": {
                "easy": {"items": [item], "leaderboard": []},
                "hard": {"items": [item], "leaderboard": []},
            }
        },
        load_game_assets(),
    )

    assert sessions["easy"].track.collision is not sessions["hard"].track.collision
    assert sessions["easy"].cars[0].car.collision_surface is sessions["easy"].track.collision
    assert sessions["hard"].cars[0].car.collision_surface is sessions["hard"].track.collision


def test_replay_session_applies_submission_skin_and_max_speed():
    from game_engine.backend.assets import load_game_assets
    from game_engine.frontend.replay_client import load_replay_sessions
    from game_engine.frontend.shop.renderer import surfaces_for

    pygame.init()
    pygame.display.set_mode((1, 1))
    assets = load_game_assets()
    item = {
        "rank": 1,
        "submission_id": "sub_demo",
        "group_id": "1",
        "username": "ada",
        "skin_id": 3,
        "max_speed": 12.5,
        "client_result": make_payload()["client_result"],
        "weights": [[0.0] * 36, [0.0] * 24],
        "biases": [[0.0] * 6, [0.0] * 4],
    }
    sessions = load_replay_sessions(
        {"replays": {"easy": {"items": [item], "leaderboard": []}}},
        assets,
    )

    replay_car = sessions["easy"].cars[0]
    assert replay_car.car.car_image is surfaces_for(3)["small"]
    assert replay_car.car.max_speed == 12.5


def test_replay_payload_identity_detects_leaderboard_and_restart_changes():
    from game_engine.frontend.replay_client import _replay_payload_identity

    def state(*, generation: int = 0, submission_id: str = "sub_a") -> dict:
        return {
            "stage": "phase_one",
            "replay_generation": generation,
            "replays": {
                "easy": {
                    "leaderboard": [
                        {"rank": 1, "submission_id": submission_id},
                    ]
                }
            },
        }

    first = state()

    assert _replay_payload_identity(first) != _replay_payload_identity(
        state(submission_id="sub_b")
    )
    assert _replay_payload_identity(first) != _replay_payload_identity(state(generation=1))


def test_replay_sessions_hide_unseen_leaderboard_until_revealed():
    from game_engine.backend.assets import load_game_assets
    from game_engine.frontend.replay_client import (
        _reveal_leaderboard_if_stopped,
        leaderboard_signature,
        load_replay_sessions,
    )

    pygame.init()
    pygame.display.set_mode((1, 1))
    item = {
        "rank": 1,
        "submission_id": "sub_demo",
        "group_id": "1",
        "username": "ada",
        "client_result": make_payload()["client_result"],
        "weights": [[0.0] * 36, [0.0] * 24],
        "biases": [[0.0] * 6, [0.0] * 4],
    }
    replay = {"items": [item], "leaderboard": [item]}
    state = {"replays": {"easy": replay}}
    revealed: dict[str, tuple[tuple[int, str], ...]] = {}
    sessions = load_replay_sessions(state, load_game_assets(), revealed)
    session = sessions["easy"]

    assert session.leaderboard_revealed is False

    session.stopped = True
    _reveal_leaderboard_if_stopped(session, 10.0, revealed)

    assert session.leaderboard_revealed is True
    assert session.reveal_highlight_until == 12.0
    assert revealed["easy"] == leaderboard_signature([item])
    restarted = load_replay_sessions(state, load_game_assets(), revealed)["easy"]
    assert restarted.leaderboard_revealed is True


def test_replay_scaled_rect_preserves_virtual_canvas_aspect_ratio():
    from game_engine.frontend.replay_client import scaled_rect_for_window

    assert scaled_rect_for_window((1600, 900)) == pygame.Rect(0, 0, 1600, 900)
    assert scaled_rect_for_window((800, 600)) == pygame.Rect(0, 75, 800, 450)
    assert scaled_rect_for_window((1920, 1080)) == pygame.Rect(0, 0, 1920, 1080)
    assert scaled_rect_for_window((1200, 900)) == pygame.Rect(0, 112, 1200, 675)


def test_replay_scale_virtual_screen_letterboxes_dummy_surface():
    from game_engine.frontend.replay_client import BACKGROUND, scale_virtual_screen

    virtual_screen = pygame.Surface((1600, 900))
    virtual_screen.fill((255, 0, 0))
    display = pygame.Surface((800, 600))

    rect = scale_virtual_screen(virtual_screen, display, (800, 600))

    assert rect == pygame.Rect(0, 75, 800, 450)
    assert display.get_at((400, 300))[:3] == (255, 0, 0)
    assert display.get_at((400, 10))[:3] == BACKGROUND


def test_empty_replay_session_stops_without_advancing_frames():
    from game_engine.frontend.replay_client import (
        ReplaySession,
        ReplayTrack,
        replay_panel_status,
    )

    pygame.init()
    competition_map = get_competition_map("hard")
    track = ReplayTrack(
        competition_map=competition_map,
        front=pygame.Surface((1600, 900)),
        collision=pygame.Surface((1600, 900), pygame.SRCALPHA),
    )
    session = ReplaySession(
        competition_id="hard",
        track=track,
        cars=[],
        leaderboard=[],
    )

    assert replay_panel_status(session) == "WAITING"
    assert session.tick() is True
    assert session.stopped is True
    assert session.frames == 0


def test_replay_stopped_car_sprite_draws_with_alpha():
    from game_engine.frontend.replay_client import _draw_replay_car_sprite

    class Car:
        x = 40
        y = 40
        angle = 180
        car_image = pygame.Surface((12, 20), pygame.SRCALPHA)

    class ReplayCar:
        car = Car()
        crashed = True
        stalled = False
        finished = False

    pygame.init()
    ReplayCar.car.car_image.fill((255, 255, 255, 255))
    surface = pygame.Surface((80, 80), pygame.SRCALPHA)

    _draw_replay_car_sprite(surface, ReplayCar())  # type: ignore[arg-type]

    assert surface.get_at((40, 40)).a == 112


def test_phase_one_draw_ticks_both_sides_without_short_circuit():
    from game_engine.frontend.replay_client import ReplayStatus, _draw_phase_one, _fonts

    class Track:
        front = pygame.Surface((1600, 900))

    class Session:
        competition_id = "demo"
        track = Track()
        cars = []
        leaderboard = []
        leaderboard_signature = ()
        leaderboard_revealed = True
        reveal_highlight_until = 0.0
        has_cars = True
        stopped = False

        def __init__(self) -> None:
            self.ticks = 0

        def tick(self) -> bool:
            self.ticks += 1
            return False

    pygame.init()
    screen = pygame.Surface((1600, 900))
    fonts = _fonts()
    easy = Session()
    hard = Session()

    finished = _draw_phase_one(  # type: ignore[arg-type]
        screen,
        easy,
        hard,
        fonts,
        ReplayStatus("重播中 · 第一階段 / EASY + HARD"),
        0.0,
        {},
    )

    assert finished is False
    assert easy.ticks == 1
    assert hard.ticks == 1


def test_reset_preserves_stage_and_clears_submissions_and_snapshots(tmp_path):
    clock = Clock()
    with make_client(tmp_path, clock) as client:
        client.post(
            "/v2/admin/config",
            headers={"X-Admin-Token": "secret"},
            json={"phase_one_batch_minutes": 2},
        )
        create_user(client, group_id="8", username="ada", password="pw8")
        submit(client, "easy", username="ada")
        process_now(client)
        client.post(
            "/v2/admin/stage",
            headers={"X-Admin-Token": "secret"},
            json={"stage": "final"},
        )
        reset = client.post("/v2/admin/reset-all", headers={"X-Admin-Token": "secret"})
        state = client.get("/v2/state").json()
        leaderboard = client.get("/v2/competitions/easy/leaderboard").json()
        admin_rows = client.get("/v2/admin/submissions", headers={"X-Admin-Token": "secret"}).json()
        users = client.get("/v2/admin/users", headers={"X-Admin-Token": "secret"}).json()

    assert reset.json() == {"status": "reset", "scope": "competition"}
    assert state["stage"] == "final"
    assert state["config"]["phase_one_batch_minutes"] == 2
    assert leaderboard == []
    assert admin_rows == []
    assert {user["group_id"] for user in users} == {"1", "8"}


def test_public_pages_and_websocket_use_v2_snapshot_payload(tmp_path):
    clock = Clock()
    with make_client(tmp_path, clock) as client:
        page = client.get("/leaderboard")
        admin = client.get("/admin")
        submit(client, "easy", username="ada")
        process_now(client)
        with client.websocket_connect("/ws/events") as websocket:
            event = websocket.receive_json()

    assert page.status_code == 200
    assert "data-competition=\"easy\"" in page.text
    assert "activeTabUsesSnapshots" in page.text
    assert "/v2/auth/login" in page.text
    assert "/v2/me/submissions" in page.text
    assert "competitionUserToken" in page.text
    assert "My Runs" in page.text
    assert "Group ${" in page.text
    assert "Stage inactive" in page.text
    assert 'if(activeCompetition === "final" || !snapshotAt)' not in page.text
    assert "setInterval(renderTiming, 1000)" in page.text
    assert admin.status_code == 200
    assert "Run Snapshot Now" in admin.text
    assert event["type"] == "competition_snapshot_updated"
    assert event["leaderboards"]["easy"][0]["username"] == "ada"
    assert event["config"]["phase_one_batch_minutes"] == 1


def test_replay_marks_a_stationary_car_as_stalled_after_stagnation_limit():
    from game_engine.backend.competition_track import CompetitionRunTracker
    from game_engine.frontend.replay_client import ReplayCar, update_replay_cars

    class StationaryCar:
        x = 143.0
        y = 450.0
        collided = False

        def update(self) -> None:
            return None

        def collision(self) -> bool:
            return False

        def feedforward(self) -> None:
            return None

        def takeAction(self) -> None:
            return None

    replay_car = ReplayCar(
        item={"rank": 1, "username": "spinner"},
        car=StationaryCar(),  # type: ignore[arg-type]
        color=(255, 255, 255),
        tracker=CompetitionRunTracker.from_metadata_path(
            get_competition_map("easy").metadata_path
        ),
    )
    for _ in range(STAGNATION_TICKS):
        update_replay_cars([replay_car])

    assert replay_car.stalled is True


def test_replay_marks_a_route_finisher_as_finished():
    from game_engine.backend.competition_track import (
        CompetitionRunTracker,
        load_competition_track_metadata,
    )
    from game_engine.backend.track_layout import cell_center
    from game_engine.frontend.replay_client import ReplayCar, update_replay_cars

    competition_map = get_competition_map("easy")
    metadata = load_competition_track_metadata(competition_map.metadata_path)
    centers = [cell_center(cell) for cell in metadata.route_cells]

    class RouteCar:
        collided = False

        def __init__(self) -> None:
            self.index = 0
            self.x, self.y = centers[0]

        def update(self) -> None:
            self.index += 1
            self.x, self.y = centers[self.index % len(centers)]

        def collision(self) -> bool:
            return False

        def feedforward(self) -> None:
            return None

        def takeAction(self) -> None:
            return None

    replay_car = ReplayCar(
        item={"rank": 1, "username": "finisher"},
        car=RouteCar(),  # type: ignore[arg-type]
        color=(255, 255, 255),
        tracker=CompetitionRunTracker.from_metadata_path(competition_map.metadata_path),
    )

    for _ in range(len(centers)):
        update_replay_cars([replay_car])

    assert replay_car.finished is False

    update_replay_cars([replay_car])

    assert replay_car.finished is True
    assert replay_car.finish_ticks == len(centers) + 1


def test_admin_can_restart_replay_generation(tmp_path):
    clock = Clock()
    with make_client(tmp_path, clock) as client:
        before = client.get("/v2/state").json()["replay_generation"]
        restart = client.post(
            "/v2/admin/replay/restart",
            headers={"X-Admin-Token": "secret"},
        )
        after = client.get("/v2/state").json()["replay_generation"]

    assert restart.status_code == 200
    assert restart.json()["replay_generation"] == before + 1
    assert after == before + 1
