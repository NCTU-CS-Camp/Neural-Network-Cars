from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from game_engine.backend.settings import PROJECT_ROOT
from shared.contracts import TrainingRecord


RECORDS_PATH = PROJECT_ROOT / "records.json"


class RecordStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or RECORDS_PATH
        if not self.path.exists():
            self._write([])

    def _read(self) -> list[dict]:
        content = self.path.read_text(encoding="utf-8")
        if not content.strip():
            return []
        return json.loads(content)

    def _write(self, records: list[dict]) -> None:
        self.path.write_text(json.dumps(records, indent=2), encoding="utf-8")

    def list_records(self) -> list[TrainingRecord]:
        return [TrainingRecord.from_dict(item) for item in self._read()]

    def get_record(self, record_id: str) -> TrainingRecord | None:
        for record in self.list_records():
            if record.record_id == record_id:
                return record
        return None

    def save_record(self, record: TrainingRecord) -> TrainingRecord:
        if not record.record_id:
            record.record_id = f"rec_{uuid4().hex[:8]}"
        records = self._read()
        records.append(record.to_dict())
        self._write(records)
        return record

    def update_record(self, record: TrainingRecord) -> None:
        records = self._read()
        for index, item in enumerate(records):
            if item["record_id"] == record.record_id:
                records[index] = record.to_dict()
                break
        self._write(records)

    def delete_record(self, record_id: str) -> None:
        records = [item for item in self._read() if item["record_id"] != record_id]
        self._write(records)

    def clear(self) -> None:
        self._write([])
