from pathlib import Path

import pytest

from game_engine.backend.environment import load_debug_mode, load_server_url


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


@pytest.mark.parametrize(
    ("value", "expected"),
    [("0", False), ("1", True)],
)
def test_debug_mode_loads_from_env_file(
    tmp_path: Path,
    value: str,
    expected: bool,
) -> None:
    path = tmp_path / ".env"
    path.write_text(f"DEBUG={value}\n", encoding="utf-8")

    assert load_debug_mode(path, environ={}) is expected


def test_debug_mode_environment_variable_overrides_env_file(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("DEBUG=0\n", encoding="utf-8")

    assert load_debug_mode(path, environ={"DEBUG": "1"}) is True


def test_debug_mode_rejects_invalid_value(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("DEBUG=true\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must be 0 or 1"):
        load_debug_mode(path, environ={})
