from __future__ import annotations

import time

from fastapi.testclient import TestClient

from server.app import create_app
from server.evaluator import OfficialEvaluator
from server.models import EvaluationResult, TrackScore
from server.storage import CompetitionStorage
from shared.contracts import EXPECTED_LAYER_SIZES, WeightPayload


def make_payload(
    *,
    nickname: str = "tester",
    fitness_score: float = 10.0,
    layer_sizes: list[int] | None = None,
    weights: list[list[float]] | None = None,
    biases: list[list[float]] | None = None,
) -> dict:
    return {
        "model_version": "v1",
        "layer_sizes": layer_sizes or list(EXPECTED_LAYER_SIZES),
        "weights": weights
        or [
            [0.0] * 36,
            [0.0] * 24,
        ],
        "biases": biases
        or [
            [0.0] * 6,
            [0.0] * 4,
        ],
        "fitness_score": fitness_score,
        "generation": 1,
        "track_id": "client",
        "track_seed": 42,
        "nickname": nickname,
    }


class FakeEvaluator:
    def evaluate(self, payload: WeightPayload) -> EvaluationResult:
        score = float(payload.fitness_score)
        track_scores = [
            TrackScore("t1", "Track 1", score, 10, False),
            TrackScore("t2", "Track 2", score / 2.0, 10, False),
            TrackScore("t3", "Track 3", score / 4.0, 10, False),
        ]
        return EvaluationResult(
            official_score=sum(track.score for track in track_scores),
            track_scores=track_scores,
            best_track_id="t1",
            best_track_score=score,
        )


def make_client(tmp_path):
    storage = CompetitionStorage(tmp_path / "competition.db")
    app = create_app(
        storage=storage,
        evaluator=FakeEvaluator(),
        start_worker=True,
        admin_token="secret",
    )
    return TestClient(app)


def wait_for_status(client: TestClient, submission_id: str, status: str) -> dict:
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        response = client.get(f"/api/submissions/{submission_id}")
        response.raise_for_status()
        data = response.json()
        if data["status"] == status:
            return data
        time.sleep(0.05)
    raise AssertionError(f"{submission_id} did not reach {status}")


def test_submission_is_evaluated_and_appears_on_leaderboard(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post("/api/submissions", json=make_payload())

        assert response.status_code == 201
        submission_id = response.json()["submission_id"]
        submission = wait_for_status(client, submission_id, "evaluated")
        leaderboard = client.get("/api/leaderboard").json()

    assert submission["official_score"] == 17.5
    assert leaderboard[0]["nickname"] == "tester"
    assert leaderboard[0]["best_submission_id"] == submission_id
    assert leaderboard[0]["track_scores"][0]["score"] == 10.0


def test_invalid_model_shape_is_rejected(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/submissions",
            json=make_payload(layer_sizes=[6, 8, 4]),
        )

    assert response.status_code == 400
    assert "layer_sizes" in response.json()["detail"]


def test_same_nickname_keeps_highest_evaluated_score(tmp_path):
    with make_client(tmp_path) as client:
        first = client.post(
            "/api/submissions",
            json=make_payload(nickname="ada", fitness_score=20.0),
        ).json()["submission_id"]
        wait_for_status(client, first, "evaluated")

        second = client.post(
            "/api/submissions",
            json=make_payload(nickname="ada", fitness_score=5.0),
        ).json()["submission_id"]
        wait_for_status(client, second, "evaluated")

        leaderboard = client.get("/api/leaderboard").json()

    assert len(leaderboard) == 1
    assert leaderboard[0]["best_submission_id"] == first
    assert leaderboard[0]["official_score"] == 35.0


def test_pending_submission_does_not_replace_evaluated_best(tmp_path):
    storage = CompetitionStorage(tmp_path / "competition.db")
    best = storage.create_submission(
        WeightPayload.from_dict(make_payload(nickname="ada", fitness_score=20.0))
    )
    storage.mark_evaluated(
        best["submission_id"],
        EvaluationResult(
            official_score=100.0,
            track_scores=[TrackScore("t1", "Track 1", 100.0, 10, False)],
            best_track_id="t1",
            best_track_score=100.0,
        ),
    )
    storage.create_submission(
        WeightPayload.from_dict(make_payload(nickname="ada", fitness_score=50.0))
    )

    leaderboard = storage.leaderboard()

    assert len(leaderboard) == 1
    assert leaderboard[0]["best_submission_id"] == best["submission_id"]
    assert leaderboard[0]["official_score"] == 100.0


def test_admin_token_controls_reset_and_featured_replay(tmp_path):
    with make_client(tmp_path) as client:
        submission_id = client.post(
            "/api/submissions",
            json=make_payload(),
        ).json()["submission_id"]
        wait_for_status(client, submission_id, "evaluated")

        denied = client.post("/api/admin/reset")
        featured = client.post(
            "/api/admin/replay",
            headers={"X-Admin-Token": "secret"},
            json={"submission_id": submission_id},
        )
        replay_items = client.get("/api/replay/top?n=5").json()["items"]
        reset = client.post(
            "/api/admin/reset",
            headers={"X-Admin-Token": "secret"},
        )

    assert denied.status_code == 401
    assert featured.status_code == 200
    assert replay_items[0]["submission_id"] == submission_id
    assert reset.status_code == 200


def test_official_evaluator_is_deterministic():
    payload = WeightPayload.from_dict(make_payload())
    evaluator = OfficialEvaluator(seconds_per_track=1)

    first = evaluator.evaluate(payload)
    second = evaluator.evaluate(payload)

    assert first.to_dict() == second.to_dict()
