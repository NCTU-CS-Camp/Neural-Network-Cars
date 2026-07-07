import random

import pytest

from game_engine.backend.settings import FPS
from game_engine.frontend.shop import gacha, store, wallet
from game_engine.frontend.shop.config import SINGLE_PULL_COST, TEN_PULL_COST
from shared.contracts import ClientResult


@pytest.fixture
def isolated_wallet(monkeypatch, tmp_path):
    identity = "1::apollo"
    state_path = tmp_path / "shop_state.json"
    load_entry = store.load_entry
    save_entry = store.save_entry

    monkeypatch.setattr(store, "active_identity", lambda: identity)
    monkeypatch.setattr(
        store,
        "load_entry",
        lambda current_identity: load_entry(current_identity, state_path),
    )
    monkeypatch.setattr(
        store,
        "save_entry",
        lambda current_identity, entry: save_entry(
            current_identity,
            entry,
            state_path,
        ),
    )
    return state_path


def test_wallet_awards_spends_and_persists_coins(isolated_wallet) -> None:
    assert wallet.balance() == 0

    wallet.award(12)

    assert wallet.balance() == 12
    assert wallet.spend(5)
    assert wallet.balance() == 7
    assert not wallet.spend(8)
    assert not wallet.spend(0)
    assert not wallet.spend(-5)
    assert wallet.balance() == 7
    assert isolated_wallet.exists()


def test_training_and_validation_rewards_are_applied_once(isolated_wallet) -> None:
    wallet.award_training_finish(2)
    result = ClientResult(
        completed=True,
        lap_ticks=10 * FPS,
        max_progress=1_000.0,
        ticks_to_max_progress=10 * FPS,
    )

    first_awards = wallet.award_validation("easy", result)
    repeated_awards = wallet.award_validation("easy", result)

    assert first_awards == [
        ("easy_val_15s", 20),
        ("easy_val_12s", 30),
        ("easy_val_10s", 40),
    ]
    assert repeated_awards == []
    assert wallet.balance() == 95


def test_gacha_deducts_exact_cost_and_rejects_insufficient_balance(
    isolated_wallet,
) -> None:
    wallet.award(SINGLE_PULL_COST + TEN_PULL_COST)

    single_result = gacha.single_pull(random.Random(1))
    ten_results = gacha.ten_pull(random.Random(2))

    assert single_result is not None
    assert ten_results is not None
    assert len(ten_results) == 10
    assert wallet.balance() == 0
    assert gacha.single_pull(random.Random(3)) is None
    assert wallet.balance() == 0


def test_delete_entry_removes_only_the_selected_users_shop_data(tmp_path) -> None:
    state_path = tmp_path / "shop_state.json"
    first_entry = store.load_entry("1::apollo", state_path)
    first_entry["coins"] = 20
    first_entry["owned_skins"] = [0, 3]
    second_entry = store.load_entry("2::wuwrh", state_path)
    second_entry["coins"] = 30
    second_entry["owned_skins"] = [0, 7]
    store.save_entry("1::apollo", first_entry, state_path)
    store.save_entry("2::wuwrh", second_entry, state_path)

    store.delete_entry("1::apollo", state_path)

    assert store.load_entry("1::apollo", state_path)["coins"] == 0
    assert store.load_entry("1::apollo", state_path)["owned_skins"] == [0]
    assert store.load_entry("2::wuwrh", state_path)["coins"] == 30
    assert store.load_entry("2::wuwrh", state_path)["owned_skins"] == [0, 7]
