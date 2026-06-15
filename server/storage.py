from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from game_engine.backend.settings import PROJECT_ROOT
from server.models import EvaluationResult, SubmissionStatus, new_submission_id, utc_now
from shared.contracts import WeightPayload


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
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS submissions (
                    submission_id TEXT PRIMARY KEY,
                    nickname TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    official_score REAL,
                    track_scores_json TEXT NOT NULL DEFAULT '[]',
                    best_track_id TEXT,
                    best_track_score REAL,
                    error_message TEXT,
                    submitted_at TEXT NOT NULL,
                    evaluated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS replay_control (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    featured_submission_id TEXT,
                    requested_at TEXT
                );

                INSERT OR IGNORE INTO replay_control (id) VALUES (1);
                """
            )

    def create_submission(self, payload: WeightPayload) -> dict[str, Any]:
        submission_id = new_submission_id()
        submitted_at = utc_now()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO submissions (
                    submission_id,
                    nickname,
                    payload_json,
                    status,
                    submitted_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    submission_id,
                    payload.nickname,
                    json.dumps(payload.to_dict()),
                    SubmissionStatus.PENDING.value,
                    submitted_at,
                ),
            )
        return self.get_submission(submission_id) or {}

    def get_submission(self, submission_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM submissions WHERE submission_id = ?",
                (submission_id,),
            ).fetchone()
        return self._row_to_submission(row) if row else None

    def list_submissions(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM submissions ORDER BY submitted_at DESC"
            ).fetchall()
        return [self._row_to_submission(row) for row in rows]

    def get_next_pending(self) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM submissions
                WHERE status = ?
                ORDER BY submitted_at ASC
                LIMIT 1
                """,
                (SubmissionStatus.PENDING.value,),
            ).fetchone()
        return self._row_to_submission(row) if row else None

    def mark_evaluating(self, submission_id: str) -> None:
        self._update_status(submission_id, SubmissionStatus.EVALUATING)

    def mark_evaluated(
        self,
        submission_id: str,
        result: EvaluationResult,
    ) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE submissions
                SET status = ?,
                    official_score = ?,
                    track_scores_json = ?,
                    best_track_id = ?,
                    best_track_score = ?,
                    error_message = NULL,
                    evaluated_at = ?
                WHERE submission_id = ?
                """,
                (
                    SubmissionStatus.EVALUATED.value,
                    result.official_score,
                    json.dumps(
                        [track_score.to_dict() for track_score in result.track_scores]
                    ),
                    result.best_track_id,
                    result.best_track_score,
                    utc_now(),
                    submission_id,
                ),
            )

    def mark_failed(self, submission_id: str, error_message: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE submissions
                SET status = ?,
                    error_message = ?,
                    evaluated_at = ?
                WHERE submission_id = ?
                """,
                (
                    SubmissionStatus.FAILED.value,
                    error_message,
                    utc_now(),
                    submission_id,
                ),
            )

    def leaderboard(self) -> list[dict[str, Any]]:
        rows = self.list_submissions()
        by_nickname: dict[str, dict[str, Any]] = {}

        for row in reversed(rows):
            nickname = row["nickname"]
            current = by_nickname.get(nickname)
            if current is None:
                by_nickname[nickname] = row
                continue

            row_evaluated = row["status"] == SubmissionStatus.EVALUATED.value
            current_evaluated = current["status"] == SubmissionStatus.EVALUATED.value
            if row_evaluated and not current_evaluated:
                by_nickname[nickname] = row
            elif row_evaluated and current_evaluated:
                if (row["official_score"] or 0.0) > (current["official_score"] or 0.0):
                    by_nickname[nickname] = row
            elif not current_evaluated and row["submitted_at"] > current["submitted_at"]:
                by_nickname[nickname] = row

        return sorted(
            (
                self._leaderboard_row(row)
                for row in by_nickname.values()
                if row["status"] != SubmissionStatus.FAILED.value
            ),
            key=lambda item: (
                item["official_score"] is not None,
                item["official_score"] or 0.0,
                item["submitted_at"],
            ),
            reverse=True,
        )

    def replay_top(self, limit: int) -> list[dict[str, Any]]:
        featured_id = self.get_featured_submission_id()
        leaderboard_rows = [
            row
            for row in self.leaderboard()
            if row["status"] == SubmissionStatus.EVALUATED.value
        ]
        ordered_ids: list[str] = []
        if featured_id:
            ordered_ids.append(featured_id)
        for row in leaderboard_rows:
            if row["best_submission_id"] not in ordered_ids:
                ordered_ids.append(row["best_submission_id"])
            if len(ordered_ids) >= limit:
                break

        items = []
        for submission_id in ordered_ids[:limit]:
            submission = self.get_submission(submission_id)
            if submission is None or submission["status"] != SubmissionStatus.EVALUATED.value:
                continue
            items.append(
                {
                    "submission_id": submission["submission_id"],
                    "nickname": submission["nickname"],
                    "official_score": submission["official_score"],
                    "track_scores": submission["track_scores"],
                    "best_track_id": submission["best_track_id"],
                    "best_track_score": submission["best_track_score"],
                    "payload": submission["payload"],
                }
            )
        return items

    def set_featured_submission(self, submission_id: str) -> dict[str, Any] | None:
        submission = self.get_submission(submission_id)
        if submission is None:
            return None

        requested_at = utc_now()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE replay_control
                SET featured_submission_id = ?,
                    requested_at = ?
                WHERE id = 1
                """,
                (submission_id, requested_at),
            )
        return {"submission_id": submission_id, "requested_at": requested_at}

    def get_featured_submission_id(self) -> str | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT featured_submission_id FROM replay_control WHERE id = 1"
            ).fetchone()
        if row is None:
            return None
        return row["featured_submission_id"]

    def reset(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM submissions")
            connection.execute(
                """
                UPDATE replay_control
                SET featured_submission_id = NULL,
                    requested_at = NULL
                WHERE id = 1
                """
            )

    def _update_status(
        self,
        submission_id: str,
        status: SubmissionStatus,
    ) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "UPDATE submissions SET status = ? WHERE submission_id = ?",
                (status.value, submission_id),
            )

    def _row_to_submission(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "submission_id": row["submission_id"],
            "nickname": row["nickname"],
            "payload": json.loads(row["payload_json"]),
            "status": row["status"],
            "official_score": row["official_score"],
            "track_scores": json.loads(row["track_scores_json"]),
            "best_track_id": row["best_track_id"],
            "best_track_score": row["best_track_score"],
            "error_message": row["error_message"],
            "submitted_at": row["submitted_at"],
            "evaluated_at": row["evaluated_at"],
        }

    def _leaderboard_row(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "nickname": row["nickname"],
            "best_submission_id": row["submission_id"],
            "official_score": row["official_score"],
            "track_scores": row["track_scores"],
            "status": row["status"],
            "submitted_at": row["submitted_at"],
            "evaluated_at": row["evaluated_at"],
        }


JsonStorage = CompetitionStorage
