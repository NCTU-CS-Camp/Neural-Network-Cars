from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from game_engine.backend.settings import PROJECT_ROOT
from server.models import (
    CompetitionPhase,
    EvaluationResult,
    OfficialMap,
    SubmissionStatus,
    new_submission_id,
    utc_now,
)
from server.official_maps import DEFAULT_OFFICIAL_MAP_IDS, list_official_maps
from shared.contracts import SubmissionPayload


class CompetitionStorage:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else PROJECT_ROOT / "server" / "competition.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            self._drop_legacy_schema(connection)
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS official_maps (
                    map_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    front_path TEXT NOT NULL,
                    back_path TEXT NOT NULL,
                    metadata_path TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS competition_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    active_phase TEXT NOT NULL,
                    personal_map_id TEXT NOT NULL,
                    group_map_id TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS submissions (
                    submission_id TEXT PRIMARY KEY,
                    phase TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    submitted_at TEXT NOT NULL,
                    evaluating_at TEXT
                );

                CREATE TABLE IF NOT EXISTS phase_results (
                    submission_id TEXT PRIMARY KEY,
                    phase TEXT NOT NULL,
                    map_id TEXT NOT NULL,
                    score_laps REAL NOT NULL,
                    frames_simulated INTEGER NOT NULL,
                    collided INTEGER NOT NULL,
                    checkpoints_completed INTEGER NOT NULL,
                    completed_laps INTEGER NOT NULL,
                    evaluated_at TEXT NOT NULL,
                    FOREIGN KEY(submission_id) REFERENCES submissions(submission_id)
                );
                """
            )
            self._seed_official_maps(connection)
            default_map_id = self._default_map_id(connection)
            connection.execute(
                """
                INSERT OR IGNORE INTO competition_state (
                    id,
                    active_phase,
                    personal_map_id,
                    group_map_id
                )
                VALUES (1, ?, ?, ?)
                """,
                (CompetitionPhase.PERSONAL.value, default_map_id, default_map_id),
            )

    def _drop_legacy_schema(self, connection: sqlite3.Connection) -> None:
        row = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'submissions'"
        ).fetchone()
        if row is None:
            return
        columns = {
            column["name"]
            for column in connection.execute("PRAGMA table_info(submissions)").fetchall()
        }
        if {"phase", "group_id", "username"}.issubset(columns):
            return
        connection.executescript(
            """
            DROP TABLE IF EXISTS submissions;
            DROP TABLE IF EXISTS phase_results;
            DROP TABLE IF EXISTS competition_state;
            DROP TABLE IF EXISTS official_maps;
            DROP TABLE IF EXISTS replay_control;
            """
        )

    def _seed_official_maps(self, connection: sqlite3.Connection) -> None:
        for official_map in list_official_maps():
            connection.execute(
                """
                INSERT OR REPLACE INTO official_maps (
                    map_id,
                    name,
                    front_path,
                    back_path,
                    metadata_path,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    official_map.map_id,
                    official_map.name,
                    official_map.front_path,
                    official_map.back_path,
                    official_map.metadata_path,
                    json.dumps(official_map.to_dict()),
                ),
            )

    def _default_map_id(self, connection: sqlite3.Connection) -> str:
        row = connection.execute(
            "SELECT map_id FROM official_maps ORDER BY map_id ASC LIMIT 1"
        ).fetchone()
        if row is not None:
            return str(row["map_id"])
        return DEFAULT_OFFICIAL_MAP_IDS[0]

    def active_phase(self) -> CompetitionPhase:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT active_phase FROM competition_state WHERE id = 1"
            ).fetchone()
        return CompetitionPhase(row["active_phase"])

    def set_active_phase(self, phase: CompetitionPhase | str) -> dict[str, Any]:
        phase_value = CompetitionPhase(phase).value
        with self._lock, self._connect() as connection:
            connection.execute(
                "UPDATE competition_state SET active_phase = ? WHERE id = 1",
                (phase_value,),
            )
        return self.competition_state()

    def competition_state(self) -> dict[str, Any]:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT active_phase, personal_map_id, group_map_id
                FROM competition_state
                WHERE id = 1
                """
            ).fetchone()
        active_phase = CompetitionPhase(row["active_phase"])
        return {
            "active_phase": active_phase.value,
            "personal_map_id": row["personal_map_id"],
            "group_map_id": row["group_map_id"],
            "active_map_id": row[f"{active_phase.value}_map_id"],
        }

    def list_official_maps(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT metadata_json FROM official_maps ORDER BY map_id ASC"
            ).fetchall()
        return [json.loads(row["metadata_json"]) for row in rows]

    def get_official_map(self, map_id: str) -> OfficialMap:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT metadata_json FROM official_maps WHERE map_id = ?",
                (map_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"official map not found: {map_id}")
        return OfficialMap.from_metadata(json.loads(row["metadata_json"]))

    def active_map(self, phase: CompetitionPhase | str | None = None) -> OfficialMap:
        phase_value = CompetitionPhase(phase or self.active_phase()).value
        with self._lock, self._connect() as connection:
            row = connection.execute(
                f"SELECT {phase_value}_map_id AS map_id FROM competition_state WHERE id = 1"
            ).fetchone()
        return self.get_official_map(row["map_id"])

    def set_phase_map(self, phase: CompetitionPhase | str, map_id: str) -> dict[str, Any]:
        phase_value = CompetitionPhase(phase).value
        self.get_official_map(map_id)
        with self._lock, self._connect() as connection:
            connection.execute(
                f"UPDATE competition_state SET {phase_value}_map_id = ? WHERE id = 1",
                (map_id,),
            )
        return self.competition_state()

    def create_submission(
        self,
        payload: SubmissionPayload,
        phase: CompetitionPhase | str | None = None,
    ) -> dict[str, Any]:
        phase_value = CompetitionPhase(phase or self.active_phase()).value
        submission_id = new_submission_id()
        submitted_at = utc_now()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO submissions (
                    submission_id,
                    phase,
                    group_id,
                    username,
                    payload_json,
                    status,
                    submitted_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    submission_id,
                    phase_value,
                    payload.group_id,
                    payload.username,
                    json.dumps(payload.to_dict()),
                    SubmissionStatus.PENDING.value,
                    submitted_at,
                ),
            )
        return self.get_submission(submission_id) or {}

    def get_submission(self, submission_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT s.*, r.map_id, r.score_laps, r.frames_simulated, r.collided,
                       r.checkpoints_completed, r.completed_laps, r.evaluated_at
                FROM submissions s
                LEFT JOIN phase_results r ON r.submission_id = s.submission_id
                WHERE s.submission_id = ?
                """,
                (submission_id,),
            ).fetchone()
        return self._row_to_submission(row) if row else None

    def list_submissions(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT s.*, r.map_id, r.score_laps, r.frames_simulated, r.collided,
                       r.checkpoints_completed, r.completed_laps, r.evaluated_at
                FROM submissions s
                LEFT JOIN phase_results r ON r.submission_id = s.submission_id
                ORDER BY s.submitted_at DESC
                """
            ).fetchall()
        return [self._row_to_submission(row) for row in rows]

    def list_pending(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT s.*, r.map_id, r.score_laps, r.frames_simulated, r.collided,
                       r.checkpoints_completed, r.completed_laps, r.evaluated_at
                FROM submissions s
                LEFT JOIN phase_results r ON r.submission_id = s.submission_id
                WHERE s.status = ?
                ORDER BY s.submitted_at ASC
                """,
                (SubmissionStatus.PENDING.value,),
            ).fetchall()
        return [self._row_to_submission(row) for row in rows]

    def mark_evaluating(self, submission_id: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE submissions
                SET status = ?, evaluating_at = ?, error_message = NULL
                WHERE submission_id = ?
                """,
                (SubmissionStatus.EVALUATING.value, utc_now(), submission_id),
            )

    def mark_evaluated(
        self,
        submission_id: str,
        result: EvaluationResult,
    ) -> None:
        evaluated_at = utc_now()
        with self._lock, self._connect() as connection:
            submission = connection.execute(
                "SELECT phase FROM submissions WHERE submission_id = ?",
                (submission_id,),
            ).fetchone()
            if submission is None:
                return
            connection.execute(
                """
                INSERT OR REPLACE INTO phase_results (
                    submission_id,
                    phase,
                    map_id,
                    score_laps,
                    frames_simulated,
                    collided,
                    checkpoints_completed,
                    completed_laps,
                    evaluated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    submission_id,
                    submission["phase"],
                    result.map_id,
                    result.score_laps,
                    result.frames_simulated,
                    int(result.collided),
                    result.checkpoints_completed,
                    result.completed_laps,
                    evaluated_at,
                ),
            )
            connection.execute(
                """
                UPDATE submissions
                SET status = ?, error_message = NULL
                WHERE submission_id = ?
                """,
                (SubmissionStatus.EVALUATED.value, submission_id),
            )

    def mark_failed(self, submission_id: str, error_message: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE submissions
                SET status = ?, error_message = ?
                WHERE submission_id = ?
                """,
                (SubmissionStatus.FAILED.value, error_message, submission_id),
            )

    def leaderboard(
        self,
        phase: CompetitionPhase | str | None = None,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        phase_value = CompetitionPhase(phase or self.active_phase()).value
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT s.*, r.map_id, r.score_laps, r.frames_simulated, r.collided,
                       r.checkpoints_completed, r.completed_laps, r.evaluated_at
                FROM submissions s
                JOIN phase_results r ON r.submission_id = s.submission_id
                WHERE s.phase = ? AND s.status = ?
                ORDER BY r.score_laps DESC, s.submitted_at ASC
                """,
                (phase_value, SubmissionStatus.EVALUATED.value),
            ).fetchall()

        by_identity: dict[str, dict[str, Any]] = {}
        for row in rows:
            submission = self._row_to_submission(row)
            identity = submission["username"] if phase_value == "personal" else submission["group_id"]
            if identity not in by_identity:
                by_identity[identity] = submission

        leaderboard = []
        for rank, submission in enumerate(by_identity.values(), start=1):
            row = self._leaderboard_row(submission, rank, phase_value)
            leaderboard.append(row)
            if len(leaderboard) >= limit:
                break
        return leaderboard

    def replay_top(self, limit: int = 10) -> list[dict[str, Any]]:
        items = []
        for row in self.leaderboard(limit=limit):
            submission = self.get_submission(row["submission_id"])
            if submission is None:
                continue
            payload = submission["payload"]
            items.append(
                {
                    "submission_id": submission["submission_id"],
                    "phase": submission["phase"],
                    "group_id": submission["group_id"],
                    "username": submission["username"],
                    "score_laps": submission["score_laps"],
                    "weights": payload["weights"],
                    "biases": payload["biases"],
                }
            )
        return items

    def best_submissions_for_phase(self, phase: CompetitionPhase | str) -> list[dict[str, Any]]:
        rows = self.leaderboard(phase=phase, limit=10_000)
        submissions = []
        for row in rows:
            submission = self.get_submission(row["submission_id"])
            if submission is not None:
                submissions.append(submission)
        return submissions

    def reset_phase(self, phase: CompetitionPhase | str | None = None) -> None:
        phase_value = CompetitionPhase(phase or self.active_phase()).value
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                DELETE FROM phase_results
                WHERE submission_id IN (
                    SELECT submission_id FROM submissions WHERE phase = ?
                )
                """,
                (phase_value,),
            )
            connection.execute("DELETE FROM submissions WHERE phase = ?", (phase_value,))

    def reset(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM phase_results")
            connection.execute("DELETE FROM submissions")

    def competition_update_payload(self) -> dict[str, Any]:
        state = self.competition_state()
        active_map = self.active_map(state["active_phase"])
        return {
            "type": "competition_updated",
            "phase": state["active_phase"],
            "map": active_map.to_dict(),
            "updated_at": utc_now(),
            "leaderboard": self.leaderboard(limit=30),
            "replay_top": self.replay_top(limit=10),
        }

    def _row_to_submission(self, row: sqlite3.Row) -> dict[str, Any]:
        payload = json.loads(row["payload_json"])
        result = None
        if row["score_laps"] is not None:
            result = {
                "map_id": row["map_id"],
                "score_laps": row["score_laps"],
                "frames_simulated": row["frames_simulated"],
                "collided": bool(row["collided"]),
                "checkpoints_completed": row["checkpoints_completed"],
                "completed_laps": row["completed_laps"],
                "evaluated_at": row["evaluated_at"],
            }
        return {
            "submission_id": row["submission_id"],
            "phase": row["phase"],
            "group_id": row["group_id"],
            "username": row["username"],
            "payload": payload,
            "weights": payload["weights"],
            "biases": payload["biases"],
            "status": row["status"],
            "error_message": row["error_message"],
            "submitted_at": row["submitted_at"],
            "evaluating_at": row["evaluating_at"],
            "map_id": result["map_id"] if result else None,
            "score_laps": result["score_laps"] if result else None,
            "frames_simulated": result["frames_simulated"] if result else None,
            "collided": result["collided"] if result else None,
            "checkpoints_completed": result["checkpoints_completed"] if result else None,
            "completed_laps": result["completed_laps"] if result else None,
            "evaluated_at": result["evaluated_at"] if result else None,
        }

    def _leaderboard_row(
        self,
        submission: dict[str, Any],
        rank: int,
        phase: str,
    ) -> dict[str, Any]:
        row = {
            "rank": rank,
            "phase": phase,
            "submission_id": submission["submission_id"],
            "group_id": submission["group_id"],
            "username": submission["username"],
            "score_laps": submission["score_laps"],
            "map_id": submission["map_id"],
            "submitted_at": submission["submitted_at"],
            "evaluated_at": submission["evaluated_at"],
        }
        if phase == "group":
            row["best_username"] = submission["username"]
        return row


JsonStorage = CompetitionStorage
