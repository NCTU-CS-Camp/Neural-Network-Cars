from __future__ import annotations

import numpy as np
import pygame
from fastapi.testclient import TestClient

from game_engine.frontend.replay_client import ReplayCar, ReplaySession
from server import evaluator as evaluator_module
from server.app import create_app
from server.evaluator import CheckpointTracker, OfficialEvaluator
from server.mock_data import create_mock_submissions
from server.models import CheckpointGate, EvaluationResult, OfficialMap
from server.storage import CompetitionStorage
from shared.contracts import SubmissionPayload


def make_payload(
    *,
    group_id: str = "1",
    username: str = "tester",
    score_hint: float = 1.0,
    weights: list[list[float]] | None = None,
    biases: list[list[float]] | None = None,
) -> dict:
    first_weights = [0.0] * 36
    first_weights[0] = score_hint
    return {
        "group_id": group_id,
        "username": username,
        "weights": weights or [first_weights, [0.0] * 24],
        "biases": biases or [[0.0] * 6, [0.0] * 4],
    }


class FakeEvaluator:
    def evaluate(
        self,
        payload: SubmissionPayload,
        official_map: OfficialMap,
    ) -> EvaluationResult:
        map_bonus = int(official_map.map_id.rsplit("_", 1)[-1]) / 100.0
        return EvaluationResult(
            score_laps=float(payload.weights[0][0]) + map_bonus,
            frames_simulated=30,
            collided=False,
            checkpoints_completed=3,
            completed_laps=0,
            map_id=official_map.map_id,
        )


def make_client(tmp_path, *, start_worker: bool = False):
    storage = CompetitionStorage(tmp_path / "competition.db")
    app = create_app(
        storage=storage,
        evaluator=FakeEvaluator(),
        start_worker=start_worker,
        admin_token="secret",
        worker_poll_interval=0.05,
    )
    return TestClient(app)


def process_pending(client: TestClient) -> int:
    response = client.post(
        "/api/admin/process-pending",
        headers={"X-Admin-Token": "secret"},
    )
    response.raise_for_status()
    return int(response.json()["processed"])


def test_new_submission_format_creates_pending_submission(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post("/api/submissions", json=make_payload())

    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    assert response.json()["phase"] == "personal"


def test_old_submission_format_and_invalid_shapes_are_rejected(tmp_path):
    old_payload = {
        "model_version": "v1",
        "layer_sizes": [6, 6, 4],
        "weights": [[0.0] * 36, [0.0] * 24],
        "biases": [[0.0] * 6, [0.0] * 4],
        "fitness_score": 1.0,
        "generation": 1,
        "track_id": "client",
        "track_seed": 42,
        "nickname": "tester",
    }
    with make_client(tmp_path) as client:
        old_response = client.post("/api/submissions", json=old_payload)
        invalid_response = client.post(
            "/api/submissions",
            json=make_payload(weights=[[0.0], [0.0] * 24]),
        )

    assert old_response.status_code == 422
    assert invalid_response.status_code == 400
    assert "weights[0]" in invalid_response.json()["detail"]


def test_submission_query_requires_admin_token(tmp_path):
    with make_client(tmp_path) as client:
        submission_id = client.post(
            "/api/submissions",
            json=make_payload(),
        ).json()["submission_id"]
        denied_list = client.get("/api/submissions")
        denied_detail = client.get(f"/api/submissions/{submission_id}")
        allowed = client.get(
            f"/api/submissions/{submission_id}",
            headers={"X-Admin-Token": "secret"},
        )

    assert denied_list.status_code == 401
    assert denied_detail.status_code == 401
    assert allowed.status_code == 200
    assert allowed.json()["username"] == "tester"


def test_pending_batch_evaluates_and_updates_personal_leaderboard(tmp_path):
    with make_client(tmp_path) as client:
        submission_id = client.post(
            "/api/submissions",
            json=make_payload(username="ada", score_hint=2.0),
        ).json()["submission_id"]
        processed = process_pending(client)
        leaderboard = client.get("/api/leaderboard").json()

    assert processed == 1
    assert leaderboard[0]["username"] == "ada"
    assert leaderboard[0]["submission_id"] == submission_id
    assert leaderboard[0]["score_laps"] == 2.01


def test_personal_leaderboard_keeps_highest_score_and_earliest_tie(tmp_path):
    with make_client(tmp_path) as client:
        first = client.post(
            "/api/submissions",
            json=make_payload(username="ada", score_hint=2.0),
        ).json()["submission_id"]
        client.post(
            "/api/submissions",
            json=make_payload(username="ada", score_hint=1.0),
        )
        process_pending(client)
        leaderboard = client.get("/api/leaderboard").json()

    assert len(leaderboard) == 1
    assert leaderboard[0]["submission_id"] == first
    assert leaderboard[0]["score_laps"] == 2.01


def test_group_phase_groups_by_group_id_and_exposes_best_username(tmp_path):
    with make_client(tmp_path) as client:
        client.post(
            "/api/admin/phase",
            headers={"X-Admin-Token": "secret"},
            json={"phase": "group"},
        )
        client.post(
            "/api/submissions",
            json=make_payload(group_id="7", username="alice", score_hint=1.0),
        )
        client.post(
            "/api/submissions",
            json=make_payload(group_id="7", username="bob", score_hint=3.0),
        )
        process_pending(client)
        leaderboard = client.get("/api/leaderboard").json()

    assert len(leaderboard) == 1
    assert leaderboard[0]["group_id"] == "7"
    assert leaderboard[0]["best_username"] == "bob"
    assert leaderboard[0]["score_laps"] == 3.01


def test_phase_switch_preserves_separate_results_and_reset_clears_active_phase(tmp_path):
    with make_client(tmp_path) as client:
        client.post(
            "/api/submissions",
            json=make_payload(username="solo", score_hint=2.0),
        )
        process_pending(client)
        personal_rows = client.get("/api/leaderboard").json()

        client.post(
            "/api/admin/phase",
            headers={"X-Admin-Token": "secret"},
            json={"phase": "group"},
        )
        group_rows_before = client.get("/api/leaderboard").json()
        client.post(
            "/api/submissions",
            json=make_payload(group_id="2", username="member", score_hint=4.0),
        )
        process_pending(client)
        group_rows_after = client.get("/api/leaderboard").json()
        reset = client.post(
            "/api/admin/reset",
            headers={"X-Admin-Token": "secret"},
        )
        group_rows_reset = client.get("/api/leaderboard").json()
        client.post(
            "/api/admin/phase",
            headers={"X-Admin-Token": "secret"},
            json={"phase": "personal"},
        )
        personal_rows_again = client.get("/api/leaderboard").json()

    assert personal_rows[0]["username"] == "solo"
    assert group_rows_before == []
    assert group_rows_after[0]["group_id"] == "2"
    assert reset.json()["phase"] == "group"
    assert group_rows_reset == []
    assert personal_rows_again[0]["username"] == "solo"


def test_reset_all_clears_both_phases_and_preserves_state(tmp_path):
    with make_client(tmp_path) as client:
        client.post(
            "/api/submissions",
            json=make_payload(username="solo", score_hint=2.0),
        )
        process_pending(client)
        client.post(
            "/api/admin/phase",
            headers={"X-Admin-Token": "secret"},
            json={"phase": "group"},
        )
        client.post(
            "/api/submissions",
            json=make_payload(group_id="2", username="member", score_hint=4.0),
        )
        process_pending(client)
        state_before = client.get("/api/state").json()

        reset = client.post(
            "/api/admin/reset-all",
            headers={"X-Admin-Token": "secret"},
        )
        state_after = client.get("/api/state").json()
        group_rows = client.get("/api/leaderboard").json()
        client.post(
            "/api/admin/phase",
            headers={"X-Admin-Token": "secret"},
            json={"phase": "personal"},
        )
        personal_rows = client.get("/api/leaderboard").json()

    assert reset.json() == {"status": "reset", "scope": "all"}
    assert state_after == state_before
    assert group_rows == []
    assert personal_rows == []


def test_map_change_reruns_best_submission_for_phase(tmp_path):
    with make_client(tmp_path) as client:
        client.post(
            "/api/submissions",
            json=make_payload(username="ada", score_hint=2.0),
        )
        process_pending(client)
        before = client.get("/api/leaderboard").json()[0]
        maps = client.get("/api/maps").json()
        new_map_id = maps[1]["map_id"]
        client.post(
            "/api/admin/map",
            headers={"X-Admin-Token": "secret"},
            json={"phase": "personal", "map_id": new_map_id},
        )
        after = client.get("/api/leaderboard").json()[0]

    assert before["map_id"] != new_map_id
    assert after["map_id"] == new_map_id
    assert after["score_laps"] == 2.02


def test_replay_top_is_public_and_contains_payload(tmp_path):
    with make_client(tmp_path) as client:
        client.post(
            "/api/submissions",
            json=make_payload(username="ada", score_hint=2.0),
        )
        process_pending(client)
        replay = client.get("/api/replay/top?n=10").json()

    assert replay["phase"] == "personal"
    assert replay["map"]["map_id"] == "official_001"
    assert replay["items"][0]["username"] == "ada"
    assert len(replay["items"][0]["weights"][0]) == 36


def test_map_preview_serves_official_track_image(tmp_path):
    with make_client(tmp_path) as client:
        map_id = client.get("/api/maps").json()[0]["map_id"]
        preview = client.get(f"/api/maps/{map_id}/preview")
        missing = client.get("/api/maps/not-a-map/preview")

    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/png"
    assert preview.content.startswith(b"\x89PNG")
    assert missing.status_code == 404


def test_websocket_sends_complete_update_after_batch(tmp_path):
    with make_client(tmp_path) as client:
        client.post(
            "/api/submissions",
            json=make_payload(username="ada", score_hint=2.0),
        )
        process_pending(client)
        with client.websocket_connect("/ws/events") as websocket:
            event = websocket.receive_json()

    assert event["type"] == "competition_updated"
    assert event["leaderboard"][0]["username"] == "ada"
    assert event["replay_top"][0]["username"] == "ada"


def test_mock_data_creates_pending_and_evaluated_submissions(tmp_path):
    storage = CompetitionStorage(tmp_path / "competition.db")
    pending = create_mock_submissions(
        storage=storage,
        evaluator=FakeEvaluator(),
        count=10,
        state="pending",
        reset=True,
    )
    evaluated = create_mock_submissions(
        storage=storage,
        evaluator=FakeEvaluator(),
        count=3,
        state="evaluated",
    )

    assert len(pending) == 10
    assert len(evaluated) == 3
    assert len(storage.leaderboard(limit=30)) == 3
    assert len(storage.replay_top(limit=10)) == 3


def test_checkpoint_tracker_advances_only_next_gate():
    tracker = CheckpointTracker(
        [
            CheckpointGate(0, (10, 5), (10, 0), (10, 10)),
            CheckpointGate(1, (20, 5), (20, 0), (20, 10)),
        ]
    )

    tracker.advance((15, 5), (25, 5))
    assert tracker.score_laps == 0

    tracker.advance((0, 5), (15, 5))
    assert tracker.score_laps == 0.5

    tracker.advance((15, 5), (25, 5))
    assert tracker.score_laps == 1.0


def test_checkpoint_tracker_no_longer_uses_large_center_radius_fallback():
    tracker = CheckpointTracker(
        [
            CheckpointGate(0, (10, 5), (10, 0), (10, 10)),
        ]
    )

    tracker.advance((20, 5), (20, 5))

    assert tracker.score_laps == 0


def test_official_evaluator_does_not_count_checkpoint_on_collision_frame(monkeypatch):
    class CollidingCheckpointCar:
        def __init__(self, sizes):
            self.weights = [
                np.zeros((sizes[1], sizes[0])),
                np.zeros((sizes[2], sizes[1])),
            ]
            self.biases = [
                np.zeros((sizes[1], 1)),
                np.zeros((sizes[2], 1)),
            ]
            self.x = 0
            self.y = 5

        def reset_state(self, x, y, angle=180, car_image=None):
            del angle, car_image
            self.x = x
            self.y = y

        def update(self):
            self.x = 15
            self.y = 5

        def collision(self):
            return True

        def feedforward(self):
            raise AssertionError("colliding frame should not feed forward")

        def takeAction(self):
            raise AssertionError("colliding frame should not take action")

    monkeypatch.setattr(evaluator_module, "Car", CollidingCheckpointCar)
    monkeypatch.setattr(
        evaluator_module.pygame.image,
        "load",
        lambda path: pygame.Surface((32, 32), pygame.SRCALPHA),
    )
    payload = SubmissionPayload.from_dict(make_payload())
    official_map = OfficialMap(
        map_id="test",
        name="Test Track",
        front_path="unused_front.png",
        back_path="unused_back.png",
        metadata_path="unused.json",
        spawn_x=0,
        spawn_y=5,
        spawn_angle=180,
        checkpoints=[CheckpointGate(0, (10, 5), (10, 0), (10, 10))],
        route_cells=[],
    )

    result = OfficialEvaluator(seconds_per_run=1).evaluate(payload, official_map)

    assert result.collided is True
    assert result.frames_simulated == 1
    assert result.checkpoints_completed == 0
    assert result.score_laps == 0


class FakeReplayCar:
    def __init__(self, collisions: list[bool]) -> None:
        self.collisions = collisions
        self.collided = False
        self.update_count = 0
        self.feedforward_count = 0
        self.action_count = 0
        self.x = 120
        self.y = 480

    def update(self) -> None:
        self.update_count += 1

    def collision(self) -> bool:
        if self.collisions:
            return self.collisions.pop(0)
        return False

    def feedforward(self) -> None:
        self.feedforward_count += 1

    def takeAction(self) -> None:
        self.action_count += 1


def test_replay_session_stops_crashed_car_but_keeps_others_running():
    crashed_car = FakeReplayCar([True])
    running_car = FakeReplayCar([False, False])
    session = ReplaySession(
        cars=[
            ReplayCar({"group_id": "1", "username": "crash"}, crashed_car, (255, 0, 0)),
            ReplayCar({"group_id": "2", "username": "run"}, running_car, (0, 255, 0)),
        ],
        frame_limit=2,
        crash_hold_frames=1,
    )

    assert session.tick() is False
    assert session.cars[0].crashed is True
    assert crashed_car.update_count == 1
    assert running_car.update_count == 1
    assert running_car.action_count == 1

    assert session.tick() is True
    assert crashed_car.update_count == 1
    assert running_car.update_count == 2
    assert running_car.action_count == 2


def test_replay_session_restarts_after_all_cars_crash_and_hold_expires():
    first_car = FakeReplayCar([True])
    second_car = FakeReplayCar([True])
    session = ReplaySession(
        cars=[
            ReplayCar({"group_id": "1", "username": "one"}, first_car, (255, 0, 0)),
            ReplayCar({"group_id": "2", "username": "two"}, second_car, (0, 255, 0)),
        ],
        frame_limit=60,
        crash_hold_frames=2,
    )

    assert session.tick() is False
    assert session.all_crashed_at_frame == 1
    assert session.tick() is False
    assert session.tick() is True
    assert first_car.update_count == 1
    assert second_car.update_count == 1


def test_official_evaluator_is_deterministic(tmp_path):
    payload = SubmissionPayload.from_dict(make_payload())
    storage = CompetitionStorage(tmp_path / "competition.db")
    official_map = storage.active_map()
    evaluator = OfficialEvaluator(seconds_per_run=1)

    first = evaluator.evaluate(payload, official_map)
    second = evaluator.evaluate(payload, official_map)

    assert first.to_dict() == second.to_dict()
