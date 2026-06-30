from __future__ import annotations

from server.storage import CompetitionStorage
from shared.contracts import ReplayRequest


class ReplayQueue:
    def __init__(self, storage: CompetitionStorage) -> None:
        self.storage = storage

    def enqueue(self, request: ReplayRequest) -> dict:
        return {
            "submission_id": request.submission_id,
            "render_mode": request.render_mode,
            "status": "retired",
        }
