import pytest

from shared.contracts import FitnessConfig


def test_config_exposes_all_ten_weights_as_properties() -> None:
    config = FitnessConfig(
        speed=1,
        progress=2,
        centered=3,
        alignment=4,
        safety=5,
        stall=6,
        spin=7,
        wrong_way=8,
        time=9,
        crash=10,
    )

    assert config.weight_names() == (
        "speed",
        "progress",
        "centered",
        "alignment",
        "safety",
        "stall",
        "spin",
        "wrong_way",
        "time",
        "crash",
    )
    assert config.speed == 1
    assert config.crash == 10
    assert config.weights == dict(zip(config.weight_names(), range(1, 11), strict=True))


def test_weights_compatibility_property_is_a_snapshot() -> None:
    config = FitnessConfig(speed=25)

    weights = config.weights
    weights["speed"] = 99

    assert config.speed == 25


def test_preset_instances_can_be_adjusted_independently() -> None:
    first = FitnessConfig.from_preset("balanced_v1")
    second = FitnessConfig.from_preset("balanced_v1")

    first.progress = 99
    first.set_weight("crash", 80)

    assert second.progress == 10
    assert second.crash == 50
    assert first.get_weight("progress") == 99
    assert first.crash == 80


def test_apply_preset_updates_existing_object() -> None:
    config = FitnessConfig(speed=100, progress=100)

    config.apply_preset("safe_finish_v1")

    assert config.speed == 15
    assert config.progress == 10
    assert config.centered == 60
    assert config.crash == 90


def test_config_serialization_preserves_resolved_weights() -> None:
    config = FitnessConfig.from_preset("progress_first_v1")
    config.progress = 33

    restored = FitnessConfig.from_dict(config.to_dict())

    assert restored == config
    assert restored.progress == 33


def test_unknown_preset_and_weight_are_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown fitness preset"):
        FitnessConfig.from_preset("missing")

    with pytest.raises(ValueError, match="unknown"):
        FitnessConfig(weights={"unknown": 1})
