from shared.contracts import RuntimeSettings


def test_runtime_settings_ignore_legacy_fitness_strategy() -> None:
    settings = RuntimeSettings.from_dict(
        {"fitness_strategy": "baseline_distance"}
    )

    assert "fitness_strategy" not in settings.to_dict()


def test_runtime_settings_load_server_url() -> None:
    settings = RuntimeSettings.from_dict(
        {"server_url": "https://competition.example.com"}
    )

    assert settings.server_url == "https://competition.example.com"
    assert settings.to_dict()["server_url"] == "https://competition.example.com"


def test_runtime_settings_default_server_url() -> None:
    settings = RuntimeSettings.from_dict({})

    assert settings.server_url == "http://127.0.0.1:8000"
