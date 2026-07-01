from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from game_engine.backend.settings import PROJECT_ROOT
from server.competition_config import (
    COMPETITION_CONFIG_VERSION,
    LEADERBOARD_LIMIT,
    PHASE_ONE_BATCH_MINUTES,
    PHASE_ONE_REPLAY_LIMIT,
    previous_batch_boundary,
    public_config,
    validate_phase_one_batch_minutes,
)
from server.competition_maps import get_competition_map, list_competition_maps
from server.models import (
    CompetitionId,
    CompetitionStage,
    SubmissionStatus,
    new_batch_id,
    new_submission_id,
)
from shared.contracts import ClientResult, SubmissionPayload


SCHEMA_VERSION = "trusted-client-v2"


class SubmissionRejected(Exception):
    def __init__(
        self,
        *,
        code: str,
        status_code: int,
        next_submission_at: str | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.next_submission_at = next_submission_at


class CompetitionStorage:
    """Persistence and ranking for trusted client-reported competition metrics."""

    def __init__(
        self,
        path: Path | str | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.path = Path(path) if path is not None else PROJECT_ROOT / "server" / "competition.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS competition_schema (version TEXT NOT NULL)"
            )
            row = connection.execute("SELECT version FROM competition_schema LIMIT 1").fetchone()
            if row is None or row["version"] != SCHEMA_VERSION:
                self._replace_schema(connection)

            columns = {
                column["name"]
                for column in connection.execute("PRAGMA table_info(competition_state)").fetchall()
            }
            if "replay_generation" not in columns:
                connection.execute(
                    """
                    ALTER TABLE competition_state
                    ADD COLUMN replay_generation INTEGER NOT NULL DEFAULT 0
                    """
                )
            if "phase_one_batch_minutes" not in columns:
                connection.execute(
                    """
                    ALTER TABLE competition_state
                    ADD COLUMN phase_one_batch_minutes INTEGER NOT NULL DEFAULT 1
                    """
                )

            connection.execute(
                """
                INSERT OR IGNORE INTO competition_state (
                    id, stage, config_version, phase_one_batch_minutes
                )
                VALUES (1, ?, ?, ?)
                """,
                (
                    CompetitionStage.PHASE_ONE.value,
                    COMPETITION_CONFIG_VERSION,
                    PHASE_ONE_BATCH_MINUTES,
                ),
            )

    def _replace_schema(self, connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            DROP TABLE IF EXISTS phase_results;
            DROP TABLE IF EXISTS submissions;
            DROP TABLE IF EXISTS batches;
            DROP TABLE IF EXISTS competition_state;
            DROP TABLE IF EXISTS official_maps;
            DROP TABLE IF EXISTS replay_control;
            DROP TABLE IF EXISTS competition_schema;

            CREATE TABLE competition_schema (
                version TEXT NOT NULL
            );

            CREATE TABLE competition_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                stage TEXT NOT NULL,
                config_version TEXT NOT NULL,
                replay_generation INTEGER NOT NULL DEFAULT 0,
                phase_one_batch_minutes INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE submissions (
                submission_id TEXT PRIMARY KEY,
                competition_id TEXT NOT NULL,
                group_id TEXT NOT NULL,
                username TEXT NOT NULL,
                weights_json TEXT NOT NULL,
                biases_json TEXT NOT NULL,
                client_result_json TEXT NOT NULL,
                status TEXT NOT NULL,
                error_message TEXT,
                submitted_at TEXT NOT NULL,
                completed_at TEXT,
                batch_id TEXT
            );

            CREATE TABLE batches (
                batch_id TEXT PRIMARY KEY,
                competition_id TEXT NOT NULL,
                window_start TEXT NOT NULL,
                window_end TEXT NOT NULL,
                created_at TEXT NOT NULL,
                snapshot_json TEXT NOT NULL
            );

            CREATE INDEX submissions_competition_status_idx
            ON submissions (competition_id, status, submitted_at);
            CREATE INDEX submissions_identity_idx
            ON submissions (competition_id, group_id, username, submitted_at);
            CREATE INDEX batches_competition_idx
            ON batches (competition_id, created_at DESC);
            """
        )
        connection.execute(
            "INSERT INTO competition_schema (version) VALUES (?)", (SCHEMA_VERSION,)
        )

    def now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def stage(self) -> CompetitionStage:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT stage FROM competition_state WHERE id = 1"
            ).fetchone()
        return CompetitionStage(row["stage"])

    def set_stage(self, stage: CompetitionStage | str) -> dict[str, Any]:
        stage_value = CompetitionStage(stage).value
        with self._lock, self._connect() as connection:
            connection.execute(
                "UPDATE competition_state SET stage = ? WHERE id = 1", (stage_value,)
            )
        return self.state()

    def set_phase_one_batch_minutes(self, minutes: int) -> dict[str, Any]:
        minutes = validate_phase_one_batch_minutes(minutes)
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE competition_state
                SET phase_one_batch_minutes = ?
                WHERE id = 1
                """,
                (minutes,),
            )
        return self.state()

    def state(self, now: datetime | None = None) -> dict[str, Any]:
        timestamp = now or self.now()
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT stage, replay_generation, phase_one_batch_minutes
                FROM competition_state
                WHERE id = 1
                """
            ).fetchone()
        stage = CompetitionStage(row["stage"])
        phase_one_batch_minutes = validate_phase_one_batch_minutes(
            int(row["phase_one_batch_minutes"])
        )
        return {
            "stage": stage.value,
            "replay_generation": int(row["replay_generation"]),
            "config": public_config(
                timestamp,
                phase_one_batch_minutes=phase_one_batch_minutes,
            ),
            "competitions": [item.to_public_dict() for item in list_competition_maps()],
        }

    def restart_replay(self) -> dict[str, Any]:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE competition_state
                SET replay_generation = replay_generation + 1
                WHERE id = 1
                """
            )
        return self.state()

    def eligibility(
        self,
        competition_id: CompetitionId | str,
        *,
        group_id: str,
        username: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        timestamp = now or self.now()
        identifier = CompetitionId(competition_id)
        with self._lock, self._connect() as connection:
            return self._eligibility_locked(
                connection,
                identifier,
                group_id=group_id,
                username=username,
                now=timestamp,
            )

    def _eligibility_locked(
        self,
        connection: sqlite3.Connection,
        competition_id: CompetitionId,
        *,
        group_id: str,
        username: str,
        now: datetime,
    ) -> dict[str, Any]:
        stage_row = connection.execute(
            """
            SELECT stage, phase_one_batch_minutes
            FROM competition_state
            WHERE id = 1
            """
        ).fetchone()
        stage = CompetitionStage(stage_row["stage"])
        phase_one_batch_minutes = validate_phase_one_batch_minutes(
            int(stage_row["phase_one_batch_minutes"])
        )
        result: dict[str, Any] = {
            "competition_id": competition_id.value,
            "stage": stage.value,
            "eligible": False,
            "reason": None,
            "next_submission_at": now.isoformat(),
            "competition_config_version": COMPETITION_CONFIG_VERSION,
        }

        if competition_id in (CompetitionId.EASY, CompetitionId.HARD):
            if stage is not CompetitionStage.PHASE_ONE:
                result["reason"] = "competition_closed"
                return result
            row = connection.execute(
                """
                SELECT submitted_at FROM submissions
                WHERE competition_id = ? AND group_id = ? AND username = ?
                  AND status != ?
                ORDER BY submitted_at DESC
                LIMIT 1
                """,
                (
                    competition_id.value,
                    group_id,
                    username,
                    SubmissionStatus.FAILED.value,
                ),
            ).fetchone()
            if row is not None:
                last_submission = _parse_timestamp(row["submitted_at"])
                next_allowed = last_submission + timedelta(
                    minutes=phase_one_batch_minutes,
                )
                result["next_submission_at"] = next_allowed.isoformat()
                if now < next_allowed:
                    result["reason"] = "submission_cooldown"
                    return result

            result["eligible"] = True
            return result

        if stage is not CompetitionStage.FINAL:
            result["reason"] = "competition_closed"
            return result

        row = connection.execute(
            """
            SELECT submitted_at FROM submissions
            WHERE competition_id = ? AND group_id = ? AND status != ?
            ORDER BY submitted_at DESC
            LIMIT 1
            """,
            (CompetitionId.FINAL.value, group_id, SubmissionStatus.FAILED.value),
        ).fetchone()
        if row is not None:
            last_submission = _parse_timestamp(row["submitted_at"])
            next_allowed = last_submission + timedelta(
                minutes=phase_one_batch_minutes,
            )
            result["next_submission_at"] = next_allowed.isoformat()
            if now < next_allowed:
                result["reason"] = "submission_cooldown"
                return result

        result["eligible"] = True
        return result

    def create_submission(
        self,
        competition_id: CompetitionId | str,
        payload: SubmissionPayload,
        client_result: ClientResult,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        identifier = CompetitionId(competition_id)
        timestamp = now or self.now()
        submitted_at = timestamp.isoformat()

        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            eligibility = self._eligibility_locked(
                connection,
                identifier,
                group_id=payload.group_id,
                username=payload.username,
                now=timestamp,
            )
            if not eligibility["eligible"]:
                status_code = 429 if eligibility["reason"] == "submission_cooldown" else 409
                raise SubmissionRejected(
                    code=str(eligibility["reason"]),
                    status_code=status_code,
                    next_submission_at=eligibility.get("next_submission_at"),
                )

            submission_id = new_submission_id()
            status = SubmissionStatus.QUEUED
            completed_at = None
            connection.execute(
                """
                INSERT INTO submissions (
                    submission_id, competition_id, group_id, username,
                    weights_json, biases_json, client_result_json, status,
                    submitted_at, completed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    submission_id,
                    identifier.value,
                    payload.group_id,
                    payload.username,
                    json.dumps(payload.weights),
                    json.dumps(payload.biases),
                    json.dumps(client_result.to_dict()),
                    status.value,
                    submitted_at,
                    completed_at,
                ),
            )

            row = connection.execute(
                "SELECT * FROM submissions WHERE submission_id = ?", (submission_id,)
            ).fetchone()
            return self._public_submission(self._submission_from_row(row))

    def seal_phase_one_batches(
        self,
        *,
        now: datetime | None = None,
        force: bool = False,
    ) -> int:
        timestamp = now or self.now()
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            interval_minutes = self._phase_one_batch_minutes_locked(connection)
            return self._seal_batches_locked(
                connection,
                (CompetitionId.EASY, CompetitionId.HARD),
                timestamp=timestamp,
                interval_minutes=interval_minutes,
                force=force,
            )

    def seal_due_batches(
        self,
        *,
        now: datetime | None = None,
        force: bool = False,
    ) -> int:
        timestamp = now or self.now()
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            stage = self._stage_locked(connection)
            interval_minutes = self._phase_one_batch_minutes_locked(connection)
            identifiers = (
                (CompetitionId.EASY, CompetitionId.HARD)
                if stage is CompetitionStage.PHASE_ONE
                else (CompetitionId.FINAL,)
            )
            return self._seal_batches_locked(
                connection,
                identifiers,
                timestamp=timestamp,
                interval_minutes=interval_minutes,
                force=force,
            )

    def _seal_batches_locked(
        self,
        connection: sqlite3.Connection,
        identifiers: tuple[CompetitionId, ...],
        *,
        timestamp: datetime,
        interval_minutes: int,
        force: bool,
    ) -> int:
        total = 0
        cutoff = (
            timestamp
            if force
            else previous_batch_boundary(
                timestamp,
                interval_minutes,
            )
        )
        window_start = cutoff - timedelta(minutes=interval_minutes)
        comparator = "<=" if force else "<"
        for identifier in identifiers:
            rows = connection.execute(
                f"""
                SELECT * FROM submissions
                WHERE competition_id = ? AND status = ? AND submitted_at {comparator} ?
                ORDER BY submitted_at ASC, submission_id ASC
                """,
                (identifier.value, SubmissionStatus.QUEUED.value, cutoff.isoformat()),
            ).fetchall()
            if not rows:
                continue

            submission_ids = [str(row["submission_id"]) for row in rows]
            placeholders = ", ".join("?" for _ in submission_ids)
            connection.execute(
                f"UPDATE submissions SET status = ? WHERE submission_id IN ({placeholders})",
                [SubmissionStatus.RUNNING.value, *submission_ids],
            )

            batch_id = new_batch_id()
            connection.execute(
                f"""
                UPDATE submissions
                SET status = ?, completed_at = ?, batch_id = ?
                WHERE submission_id IN ({placeholders})
                """,
                [
                    SubmissionStatus.COMPLETED.value,
                    timestamp.isoformat(),
                    batch_id,
                    *submission_ids,
                ],
            )
            leaderboard = self._public_leaderboard_locked(connection, identifier)
            snapshot = {
                "competition_id": identifier.value,
                "submission_ids": submission_ids,
                "leaderboard": leaderboard,
            }
            connection.execute(
                """
                INSERT INTO batches (batch_id, competition_id, window_start, window_end, created_at, snapshot_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id,
                    identifier.value,
                    window_start.isoformat(),
                    cutoff.isoformat(),
                    timestamp.isoformat(),
                    json.dumps(snapshot),
                ),
            )
            total += len(submission_ids)
        return total

    def get_submission(
        self,
        competition_id: CompetitionId | str,
        submission_id: str,
        *,
        include_model: bool = False,
    ) -> dict[str, Any] | None:
        identifier = CompetitionId(competition_id)
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM submissions
                WHERE competition_id = ? AND submission_id = ?
                """,
                (identifier.value, submission_id),
            ).fetchone()
        if row is None:
            return None
        submission = self._submission_from_row(row)
        return submission if include_model else self._public_submission(submission)

    def list_submissions(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM submissions ORDER BY submitted_at DESC, submission_id DESC"
            ).fetchall()
        return [self._submission_from_row(row) for row in rows]

    def leaderboard(
        self,
        competition_id: CompetitionId | str,
        *,
        limit: int = LEADERBOARD_LIMIT,
    ) -> list[dict[str, Any]]:
        identifier = CompetitionId(competition_id)
        with self._lock, self._connect() as connection:
            rows = self._public_leaderboard_locked(connection, identifier)
        return rows[:limit]

    def _public_leaderboard_locked(
        self,
        connection: sqlite3.Connection,
        competition_id: CompetitionId,
    ) -> list[dict[str, Any]]:
        rows = connection.execute(
            """
            SELECT * FROM submissions
            WHERE competition_id = ? AND status = ?
            ORDER BY submitted_at ASC, submission_id ASC
            """,
            (competition_id.value, SubmissionStatus.COMPLETED.value),
        ).fetchall()
        submissions = [self._submission_from_row(row) for row in rows]
        submissions.sort(key=self._ranking_key)

        best_by_identity: dict[tuple[str, ...], dict[str, Any]] = {}
        for submission in submissions:
            identity: tuple[str, ...]
            if competition_id is CompetitionId.FINAL:
                identity = (str(submission["group_id"]),)
            else:
                identity = (str(submission["group_id"]), str(submission["username"]))
            best_by_identity.setdefault(identity, submission)

        result = []
        for rank, submission in enumerate(best_by_identity.values(), start=1):
            public = self._public_submission(submission)
            public["rank"] = rank
            result.append(public)
        return result

    def _ranking_key(self, submission: dict[str, Any]) -> tuple[Any, ...]:
        client_result = ClientResult.from_dict(submission["client_result"])
        return (*client_result.ranking_key(), submission["submitted_at"], submission["submission_id"])

    @staticmethod
    def _stage_locked(connection: sqlite3.Connection) -> CompetitionStage:
        row = connection.execute(
            """
            SELECT stage
            FROM competition_state
            WHERE id = 1
            """
        ).fetchone()
        return CompetitionStage(row["stage"])

    def replay_payload(self) -> dict[str, Any]:
        state = self.state()
        stage = CompetitionStage(state["stage"])
        identifiers = (
            (CompetitionId.EASY, CompetitionId.HARD)
            if stage is CompetitionStage.PHASE_ONE
            else (CompetitionId.FINAL,)
        )
        replays = {}
        for identifier in identifiers:
            replay_map = get_competition_map(identifier)
            replays[identifier.value] = {
                "map": replay_map.to_public_dict(),
                "leaderboard": self.leaderboard(identifier, limit=LEADERBOARD_LIMIT),
                "items": self._replay_items(identifier),
            }
        return {
            "stage": state["stage"],
            "replay_generation": state["replay_generation"],
            "config": state["config"],
            "replays": replays,
        }

    def _replay_items(self, competition_id: CompetitionId) -> list[dict[str, Any]]:
        with self._lock, self._connect() as connection:
            ranked = self._public_leaderboard_locked(connection, competition_id)
            items = []
            for entry in ranked[:PHASE_ONE_REPLAY_LIMIT]:
                row = connection.execute(
                    "SELECT * FROM submissions WHERE submission_id = ?",
                    (entry["submission_id"],),
                ).fetchone()
                if row is None:
                    continue
                submission = self._submission_from_row(row)
                items.append(
                    {
                        "rank": entry["rank"],
                        "submission_id": submission["submission_id"],
                        "group_id": submission["group_id"],
                        "username": submission["username"],
                        "client_result": submission["client_result"],
                        "weights": submission["weights"],
                        "biases": submission["biases"],
                    }
                )
        return items

    def latest_snapshot(self, competition_id: CompetitionId | str) -> dict[str, Any] | None:
        identifier = CompetitionId(competition_id)
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT batch_id, window_start, window_end, created_at, snapshot_json
                FROM batches WHERE competition_id = ?
                ORDER BY created_at DESC, batch_id DESC LIMIT 1
                """,
                (identifier.value,),
            ).fetchone()
        if row is None:
            return None
        return {
            "batch_id": row["batch_id"],
            "window_start": row["window_start"],
            "window_end": row["window_end"],
            "created_at": row["created_at"],
            "snapshot": json.loads(row["snapshot_json"]),
        }

    def reset(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM batches")
            connection.execute("DELETE FROM submissions")

    def competition_update_payload(self) -> dict[str, Any]:
        state = self.state()
        return {
            "type": "competition_snapshot_updated",
            "stage": state["stage"],
            "config": state["config"],
            "leaderboards": {
                identifier.value: self.leaderboard(identifier)
                for identifier in CompetitionId
            },
            "updated_at": self.now().isoformat(),
        }

    def _submission_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "submission_id": row["submission_id"],
            "competition_id": row["competition_id"],
            "group_id": row["group_id"],
            "username": row["username"],
            "weights": json.loads(row["weights_json"]),
            "biases": json.loads(row["biases_json"]),
            "client_result": json.loads(row["client_result_json"]),
            "status": row["status"],
            "error_message": row["error_message"],
            "submitted_at": row["submitted_at"],
            "completed_at": row["completed_at"],
            "batch_id": row["batch_id"],
            "competition_config_version": COMPETITION_CONFIG_VERSION,
        }

    @staticmethod
    def _phase_one_batch_minutes_locked(connection: sqlite3.Connection) -> int:
        row = connection.execute(
            """
            SELECT phase_one_batch_minutes
            FROM competition_state
            WHERE id = 1
            """
        ).fetchone()
        return validate_phase_one_batch_minutes(int(row["phase_one_batch_minutes"]))

    @staticmethod
    def _public_submission(submission: dict[str, Any]) -> dict[str, Any]:
        return {
            key: submission[key]
            for key in (
                "submission_id",
                "competition_id",
                "group_id",
                "username",
                "client_result",
                "status",
                "error_message",
                "submitted_at",
                "completed_at",
                "batch_id",
                "competition_config_version",
            )
        }


def _parse_timestamp(value: str) -> datetime:
    timestamp = datetime.fromisoformat(value)
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC)


JsonStorage = CompetitionStorage
