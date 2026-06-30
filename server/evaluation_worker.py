from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Callable

from server.storage import CompetitionStorage


logger = logging.getLogger(__name__)


class BatchWorker:
    """Seals trusted client-result submissions at Phase 1 replay boundaries."""

    def __init__(
        self,
        storage: CompetitionStorage,
        *,
        poll_interval: float = 5.0,
        publish_update: Callable[[dict], None] | None = None,
    ) -> None:
        self.storage = storage
        self.poll_interval = poll_interval
        self.publish_update = publish_update
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def process_due(self, now: datetime | None = None) -> int:
        processed = self.storage.seal_phase_one_batches(now=now)
        if processed:
            self._publish_update()
        return processed

    def process_now(self, now: datetime | None = None) -> int:
        processed = self.storage.seal_phase_one_batches(now=now, force=True)
        if processed:
            self._publish_update()
        return processed

    def _publish_update(self) -> None:
        if self.publish_update is not None:
            self.publish_update(self.storage.competition_update_payload())

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.process_due()
            except Exception:
                logger.exception(
                    "Phase-one batch processing failed; retrying after poll interval"
                )
            self._stop_event.wait(self.poll_interval)


# The old name is retained for imports outside the competition service.
EvaluationWorker = BatchWorker
