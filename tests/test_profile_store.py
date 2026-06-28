from pathlib import Path

import pytest

from game_engine.frontend.profile_store import load_login_profile


@pytest.mark.parametrize(
    "content",
    [
        "",
        "   \n",
        "{invalid json",
        "{}",
        "[]",
    ],
)
def test_invalid_profile_is_treated_as_logged_out(
    tmp_path: Path,
    content: str,
) -> None:
    path = tmp_path / "profile.json"
    path.write_text(content, encoding="utf-8")

    assert load_login_profile(path) is None


def test_valid_profile_is_loaded(tmp_path: Path) -> None:
    path = tmp_path / "profile.json"
    path.write_text(
        (
            '{"group_id": "group-1", "username": "apollo", '
            '"server_url": "http://localhost:8000"}'
        ),
        encoding="utf-8",
    )

    profile = load_login_profile(path)

    assert profile is not None
    assert profile.group_id == "group-1"
    assert profile.username == "apollo"
    assert profile.server_url == "http://localhost:8000"
