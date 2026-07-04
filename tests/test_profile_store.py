from datetime import UTC, datetime
from pathlib import Path

import pytest

import game_engine.frontend.app as app_module
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
    assert profile.nickname == "apollo"
    assert profile.server_url == "http://localhost:8000"
    assert profile.token == ""
    assert profile.expires_at == ""


def test_profile_preserves_server_nickname(tmp_path: Path) -> None:
    path = tmp_path / "profile.json"
    path.write_text(
        '{"group_id":"1","username":"apollo","nickname":"Apollo Driver"}',
        encoding="utf-8",
    )

    profile = load_login_profile(path)

    assert profile is not None
    assert profile.display_name == "Apollo Driver"


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


def test_clear_current_user_data_clears_profile_records_presets_and_shop(
    monkeypatch,
) -> None:
    calls: list[tuple[str, str | None]] = []

    monkeypatch.setattr(
        app_module.shop_store,
        "active_identity",
        lambda: "1::apollo",
    )
    monkeypatch.setattr(
        app_module.shop_store,
        "delete_entry",
        lambda identity: calls.append(("shop", identity)),
    )

    class FakePresetStore:
        def clear(self) -> None:
            calls.append(("presets", None))

    class FakeRecordStore:
        def clear(self) -> None:
            calls.append(("records", None))

    monkeypatch.setattr(app_module, "FitnessPresetStore", FakePresetStore)
    monkeypatch.setattr(app_module, "RecordStore", FakeRecordStore)
    monkeypatch.setattr(
        app_module,
        "clear_login_profile",
        lambda: calls.append(("profile", None)),
    )

    app_module._clear_current_user_data()

    assert calls == [
        ("shop", "1::apollo"),
        ("presets", None),
        ("records", None),
        ("profile", None),
    ]


def test_logout_current_user_only_clears_profile(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        app_module,
        "clear_login_profile",
        lambda: calls.append("profile"),
    )
    monkeypatch.setattr(
        app_module.shop_store,
        "active_identity",
        lambda: calls.append("active_identity"),
    )
    monkeypatch.setattr(
        app_module.shop_store,
        "delete_entry",
        lambda identity: calls.append(f"shop:{identity}"),
    )

    class FakePresetStore:
        def clear(self) -> None:
            calls.append("presets")

    class FakeRecordStore:
        def clear(self) -> None:
            calls.append("records")

    monkeypatch.setattr(app_module, "FitnessPresetStore", FakePresetStore)
    monkeypatch.setattr(app_module, "RecordStore", FakeRecordStore)

    app_module._logout_current_user()

    assert calls == ["profile"]
