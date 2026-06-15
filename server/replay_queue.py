from __future__ import annotations

from server.storage import CompetitionStorage
from shared.contracts import ReplayRequest


class ReplayQueue:
    def __init__(self, storage: CompetitionStorage) -> None:
        self.storage = storage

    def enqueue(self, request: ReplayRequest) -> dict:
        result = self.storage.set_featured_submission(request.submission_id)
        if result is None:
            return {
                "submission_id": request.submission_id,
                "status": "missing",
            }
        return {
            "submission_id": request.submission_id,
            "track_seed": request.track_seed,
            "render_mode": request.render_mode,
            "status": "featured",
            "requested_at": result["requested_at"],
        }
