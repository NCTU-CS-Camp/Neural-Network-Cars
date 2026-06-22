from __future__ import annotations

import threading
from typing import Callable, Protocol

from server.models import EvaluationResult, OfficialMap
from server.storage import CompetitionStorage
from shared.contracts import SubmissionPayload


class Evaluator(Protocol):
    def evaluate(
        self,
        payload: SubmissionPayload,
        official_map: OfficialMap,
    ) -> EvaluationResult:
        ...


class EvaluationWorker:
    def __init__(
        self,
        storage: CompetitionStorage,
        evaluator: Evaluator,
        poll_interval: float = 60.0,
        publish_update: Callable[[dict], None] | None = None,
    ) -> None:
        self.storage = storage
        self.evaluator = evaluator
        self.poll_interval = poll_interval
        self.publish_update = publish_update
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

    def process_pending_batch(self) -> int:
        submissions = self.storage.list_pending()
        processed = 0
        for submission in submissions:
            self._evaluate_submission(submission)
            processed += 1
        if processed:
            self._publish_update()
        return processed

    def rerun_best_for_phase(self, phase: str) -> int:
        submissions = self.storage.best_submissions_for_phase(phase)
        processed = 0
        for submission in submissions:
            self._evaluate_submission(submission)
            processed += 1
        self._publish_update()
        return processed

    def _evaluate_submission(self, submission: dict) -> None:
        submission_id = submission["submission_id"]
        self.storage.mark_evaluating(submission_id)
        try:
            payload = SubmissionPayload.from_dict(submission["payload"])
            official_map = self.storage.active_map(submission["phase"])
            result = self.evaluator.evaluate(payload, official_map)
        except Exception as exc:  # noqa: BLE001 - keep evaluator failures recorded.
            self.storage.mark_failed(submission_id, str(exc))
            return
        self.storage.mark_evaluated(submission_id, result)

    def _publish_update(self) -> None:
        if self.publish_update is not None:
            self.publish_update(self.storage.competition_update_payload())

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self.process_pending_batch()
            self._stop_event.wait(self.poll_interval)
