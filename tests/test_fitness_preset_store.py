from game_engine.backend.fitness_preset_store import FitnessPresetStore
from shared.contracts import FitnessConfig


def test_clear_removes_all_custom_fitness_presets(tmp_path) -> None:
    preset_store = FitnessPresetStore(tmp_path / "fitness_presets.json")
    preset_store.save_preset("自訂參數", FitnessConfig(progress=50))
    assert len(preset_store.list_presets()) == 1

    preset_store.clear()

    assert preset_store.list_presets() == []
