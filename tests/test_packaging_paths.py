from pathlib import Path

from game_engine.backend import settings
from game_engine.frontend import config_store


def test_frozen_windows_data_uses_local_app_data(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "IS_FROZEN", True)
    monkeypatch.setattr(settings.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert settings._user_data_dir() == tmp_path / "NeuralNetworkCars"


def test_source_data_stays_in_project(monkeypatch) -> None:
    monkeypatch.setattr(settings, "IS_FROZEN", False)

    assert settings._user_data_dir() == settings.PROJECT_ROOT


def test_first_launch_uses_bundled_client_server_url(
    monkeypatch,
    tmp_path: Path,
) -> None:
    defaults_path = tmp_path / "client_defaults.json"
    defaults_path.write_text(
        '{"server_url": "https://cars.example.com"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(config_store, "CLIENT_DEFAULTS_PATH", defaults_path)
    settings_path = tmp_path / "settings.json"

    runtime_settings = config_store.load_runtime_settings(settings_path)

    assert runtime_settings.server_url == "https://cars.example.com"
    assert settings_path.exists()


def test_frozen_client_overrides_saved_server_url(
    monkeypatch,
    tmp_path: Path,
) -> None:
    defaults_path = tmp_path / "client_defaults.json"
    defaults_path.write_text(
        '{"server_url": "http://192.168.15.1:8000"}',
        encoding="utf-8",
    )
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        '{"server_url": "http://127.0.0.1:8000"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(config_store, "CLIENT_DEFAULTS_PATH", defaults_path)
    monkeypatch.setattr(config_store, "IS_FROZEN", True)

    runtime_settings = config_store.load_runtime_settings(settings_path)

    assert runtime_settings.server_url == "http://192.168.15.1:8000"
