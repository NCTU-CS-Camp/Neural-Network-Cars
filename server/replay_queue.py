from __future__ import annotations

from server.storage import CompetitionStorage
from shared.contracts import ReplayRequest


class ReplayQueue:
    def __init__(self, storage: CompetitionStorage) -> None:
        self.storage = storage

    def enqueue(self, request: ReplayRequest) -> dict:
        submission = self.storage.get_submission(request.submission_id)
        if submission is None:
            return {
                "submission_id": request.submission_id,
                "status": "missing",
            }
        return {
            "submission_id": request.submission_id,
            "render_mode": request.render_mode,
            "status": "available",
        }
