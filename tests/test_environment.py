from pathlib import Path

import pytest

from game_engine.backend.environment import load_server_url


def test_server_url_loads_from_env_file(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text(
        "COMPETITION_SERVER_URL=http://192.168.1.20:8000\n",
        encoding="utf-8",
    )

    assert load_server_url(path, environ={}) == "http://192.168.1.20:8000"


def test_environment_variable_overrides_env_file(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text(
        "COMPETITION_SERVER_URL=http://192.168.1.20:8000\n",
        encoding="utf-8",
    )

    assert load_server_url(
        path,
        environ={"COMPETITION_SERVER_URL": "https://competition.example.com/"},
    ) == "https://competition.example.com"


def test_server_url_rejects_missing_protocol(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text(
        "COMPETITION_SERVER_URL=192.168.1.20:8000\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must start"):
        load_server_url(path, environ={})
