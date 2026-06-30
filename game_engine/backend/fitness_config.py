from __future__ import annotations

import json
from pathlib import Path

from game_engine.backend.settings import PROJECT_ROOT
from shared.contracts import FitnessConfig


DEFAULT_FITNESS_CONFIG_PATH = PROJECT_ROOT / "configs" / "beginner_mix.json"


def load_fitness_config(
    path: Path = DEFAULT_FITNESS_CONFIG_PATH,
) -> FitnessConfig:
    data = json.loads(path.read_text(encoding="utf-8"))
    return FitnessConfig.from_dict(data)
