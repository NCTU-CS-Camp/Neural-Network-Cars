from __future__ import annotations

from server.models import ReplayJob
from server.storage import JsonStorage
from shared.contracts import ReplayRequest


class ReplayQueue:
    def __init__(self, storage: JsonStorage) -> None:
        self.storage = storage

    def enqueue(self, request: ReplayRequest) -> dict:
        job = ReplayJob.create(request)
        return self.storage.add_replay_job(job.to_dict())

