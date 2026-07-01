from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from GA.fitness import fitness_strategy_names
from game_engine.backend.settings import PROJECT_ROOT
from shared.contracts import CustomFitnessPreset, FitnessConfig


PRESETS_PATH = PROJECT_ROOT / "configs" / "fitness_presets.json"
SCHEMA_VERSION = 1


class FitnessPresetStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or PRESETS_PATH
        if not self.path.exists():
            self._write([])

    def _read(self) -> list[dict]:
        content = self.path.read_text(encoding="utf-8")
        if not content.strip():
            return []
        return json.loads(content).get("presets", [])

    def _write(self, presets: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"schema_version": SCHEMA_VERSION, "presets": presets}, indent=2),
            encoding="utf-8",
        )

    def list_presets(self) -> list[CustomFitnessPreset]:
        return [CustomFitnessPreset.from_dict(item) for item in self._read()]

    def save_preset(self, name: str, fitness_config: FitnessConfig) -> CustomFitnessPreset | None:
        if name in fitness_strategy_names():
            return None

        presets = self._read()
        preset_id = None
        for item in presets:
            if item["preset_name"] == name:
                preset_id = item["preset_id"]
                break

        preset = CustomFitnessPreset(
            preset_id=preset_id or f"preset_{uuid4().hex[:8]}",
            preset_name=name,
            fitness_config=fitness_config.copy(),
        )
        presets = [item for item in presets if item["preset_name"] != name]
        presets.append(preset.to_dict())
        self._write(presets)
        return preset

    def delete_preset(self, preset_id: str) -> None:
        presets = [item for item in self._read() if item["preset_id"] != preset_id]
        self._write(presets)
