from __future__ import annotations

import json
from pathlib import Path

from backend.settings import PROJECT_ROOT


class JsonStorage:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or PROJECT_ROOT / "server" / "data.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({"submissions": [], "replay_jobs": []})

    def _read(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def list_submissions(self) -> list[dict]:
        return self._read()["submissions"]

    def get_submission(self, submission_id: str) -> dict | None:
        for submission in self.list_submissions():
            if submission["submission_id"] == submission_id:
                return submission
        return None

    def add_submission(self, submission: dict) -> dict:
        data = self._read()
        data["submissions"].append(submission)
        self._write(data)
        return submission

    def list_replay_jobs(self) -> list[dict]:
        return self._read()["replay_jobs"]

    def add_replay_job(self, replay_job: dict) -> dict:
        data = self._read()
        data["replay_jobs"].append(replay_job)
        self._write(data)
        return replay_job

    def leaderboard(self) -> list[dict]:
        submissions = self.list_submissions()
        return sorted(
            submissions,
            key=lambda item: item["payload"].get("fitness_score", 0.0),
            reverse=True,
        )

