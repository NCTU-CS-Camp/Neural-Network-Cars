from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pygame
from fastapi.testclient import TestClient

from server.app import create_app
from server.competition_config import STAGNATION_TICKS
from server.competition_maps import get_competition_map
from server.storage import CompetitionStorage


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


def submit(client: TestClient, competition_id: str, **kwargs) -> dict:
    response = client.post(
        f"/v2/competitions/{competition_id}/submissions",
        json=make_payload(**kwargs),
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


def test_phase_one_submission_is_queued_and_cooldown_is_per_competition(tmp_path):
    clock = Clock()
    with make_client(tmp_path, clock) as client:
        eligibility = client.post(
            "/v2/competitions/easy/eligibility",
            json={"group_id": "1", "username": "ada"},
        )
        first = submit(client, "easy", username="ada")
        easy_again = client.post(
            "/v2/competitions/easy/eligibility",
            json={"group_id": "1", "username": "ada"},
        )
        hard = client.post(
            "/v2/competitions/hard/eligibility",
            json={"group_id": "1", "username": "ada"},
        )
        duplicate = client.post(
            "/v2/competitions/easy/submissions",
            json=make_payload(username="ada"),
        )

    assert eligibility.json()["eligible"] is True
    assert first["status"] == "queued"
    assert easy_again.json()["reason"] == "submission_cooldown"
    assert hard.json()["eligible"] is True
    assert duplicate.status_code == 429
    assert duplicate.json()["error"] == "submission_cooldown"


def test_batch_boundary_seals_queued_submissions_and_persists_snapshot(tmp_path):
    clock = Clock()
    storage = CompetitionStorage(tmp_path / "competition.db", clock=clock)
    from shared.contracts import ClientResult, SubmissionPayload

    payload = SubmissionPayload("1", "ada", [[0.0] * 36, [0.0] * 24], [[0.0] * 6, [0.0] * 4])
    storage.create_submission("easy", payload, ClientResult(False, None, 1_200.0, 300))

    assert storage.seal_phase_one_batches(now=clock.current) == 0
    clock.advance(minutes=4)
    assert storage.seal_phase_one_batches(now=clock.current) == 1
    leaderboard = storage.leaderboard("easy")
    snapshot = storage.latest_snapshot("easy")

    assert leaderboard[0]["status"] == "completed"
    assert snapshot is not None
    assert snapshot["snapshot"]["submission_ids"] == [leaderboard[0]["submission_id"]]


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


def test_final_stage_gates_submissions_and_locks_one_model_per_group(tmp_path):
    clock = Clock()
    with make_client(tmp_path, clock) as client:
        closed = client.post("/v2/finals/submissions", json=make_payload(group_id="1", username="ada"))
        stage = client.post(
            "/v2/admin/stage",
            headers={"X-Admin-Token": "secret"},
            json={"stage": "final"},
        )
        first = client.post(
            "/v2/finals/submissions",
            json=make_payload(group_id="1", username="ada", completed=True, lap_ticks=520),
        )
        duplicate = client.post(
            "/v2/finals/submissions",
            json=make_payload(group_id="1", username="ben", completed=True, lap_ticks=400),
        )
        other = client.post(
            "/v2/finals/submissions",
            json=make_payload(group_id="2", username="cy", completed=True, lap_ticks=480),
        )
        leaderboard = client.get("/v2/competitions/final/leaderboard").json()

    assert closed.status_code == 409
    assert stage.json()["stage"] == "final"
    assert first.status_code == 201
    assert first.json()["status"] == "completed"
    assert duplicate.status_code == 409
    assert duplicate.json()["error"] == "final_locked"
    assert other.status_code == 201
    assert [row["group_id"] for row in leaderboard] == ["2", "1"]


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
        )

    assert eligibility.status_code == 200
    assert eligibility.json()["eligible"] is True


def test_submission_validation_rejects_bad_client_result_shape_and_non_finite_genes(tmp_path):
    clock = Clock()
    with make_client(tmp_path, clock) as client:
        bad_result = make_payload(lap_ticks=20)
        bad_result["client_result"]["lap_ticks"] = 20
        result_response = client.post("/v2/competitions/easy/submissions", json=bad_result)

        bad_shape = make_payload()
        bad_shape["weights"][0] = [0.0]
        shape_response = client.post("/v2/competitions/easy/submissions", json=bad_shape)

        non_finite = make_payload()
        non_finite["weights"][0][0] = float("nan")
        finite_response = client.post(
            "/v2/competitions/easy/submissions",
            content=json.dumps(non_finite),
            headers={"Content-Type": "application/json"},
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


def test_reset_preserves_stage_and_clears_submissions_and_snapshots(tmp_path):
    clock = Clock()
    with make_client(tmp_path, clock) as client:
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

    assert reset.json() == {"status": "reset", "scope": "competition"}
    assert state["stage"] == "final"
    assert leaderboard == []
    assert admin_rows == []


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
    assert admin.status_code == 200
    assert "Create Demo Snapshot" in admin.text
    assert event["type"] == "competition_snapshot_updated"
    assert event["leaderboards"]["easy"][0]["username"] == "ada"


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
            self.index = min(self.index + 1, len(centers))
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

    assert replay_car.finished is True
    assert replay_car.finish_ticks == len(centers)


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
