from pathlib import Path

from game_engine.backend.record_store import RecordStore


def test_empty_records_file_is_treated_as_empty_list(tmp_path: Path) -> None:
    path = tmp_path / "records.json"
    path.write_text("", encoding="utf-8")

    assert RecordStore(path).list_records() == []
