from __future__ import annotations

import threading
import time
from typing import Protocol

from server.models import EvaluationResult
from server.storage import CompetitionStorage
from shared.contracts import WeightPayload


class Evaluator(Protocol):
    def evaluate(self, payload: WeightPayload) -> EvaluationResult:
        ...


class EvaluationWorker:
    def __init__(
        self,
        storage: CompetitionStorage,
        evaluator: Evaluator,
        poll_interval: float = 0.25,
    ) -> None:
        self.storage = storage
        self.evaluator = evaluator
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def process_pending_once(self) -> bool:
        submission = self.storage.get_next_pending()
        if submission is None:
            return False

        submission_id = submission["submission_id"]
        self.storage.mark_evaluating(submission_id)
        try:
            payload = WeightPayload.from_dict(submission["payload"])
            result = self.evaluator.evaluate(payload)
        except Exception as exc:  # noqa: BLE001 - keep evaluator failures recorded.
            self.storage.mark_failed(submission_id, str(exc))
            return True

        self.storage.mark_evaluated(submission_id, result)
        return True

    def _run(self) -> None:
        while not self._stop_event.is_set():
            processed = self.process_pending_once()
            if not processed:
                time.sleep(self.poll_interval)
