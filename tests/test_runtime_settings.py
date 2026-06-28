from shared.contracts import RuntimeSettings


def test_runtime_settings_ignore_legacy_fitness_strategy() -> None:
    settings = RuntimeSettings.from_dict(
        {"fitness_strategy": "baseline_distance"}
    )

    assert "fitness_strategy" not in settings.to_dict()
