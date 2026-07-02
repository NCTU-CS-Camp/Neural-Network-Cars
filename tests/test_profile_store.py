from datetime import UTC, datetime
from pathlib import Path

import pytest

from game_engine.frontend.profile_store import (
    clear_login_profile,
    login_session_is_valid,
    load_login_profile,
)
from shared.contracts import LoginProfile


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
    assert profile.token == ""
    assert profile.expires_at == ""


def test_login_session_requires_unexpired_token() -> None:
    now = datetime(2026, 7, 3, 2, 0, tzinfo=UTC)
    valid = LoginProfile(
        group_id="1",
        username="apollo",
        token="token",
        expires_at="2026-07-03T03:00:00+00:00",
    )
    expired = LoginProfile(
        group_id="1",
        username="apollo",
        token="token",
        expires_at="2026-07-03T01:00:00+00:00",
    )

    assert login_session_is_valid(valid, now=now)
    assert not login_session_is_valid(expired, now=now)


def test_clear_login_profile_deletes_file(tmp_path: Path) -> None:
    path = tmp_path / "profile.json"
    path.write_text("{}", encoding="utf-8")

    clear_login_profile(path)

    assert not path.exists()
