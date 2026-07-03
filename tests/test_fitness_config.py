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


def test_config_copies_can_be_adjusted_independently() -> None:
    first = FitnessConfig(progress=10, crash=50)
    second = first.copy()

    first.progress = 99
    first.set_weight("crash", 80)

    assert second.progress == 10
    assert second.crash == 50
    assert first.get_weight("progress") == 99
    assert first.crash == 80


def test_config_serialization_preserves_resolved_weights() -> None:
    config = FitnessConfig(speed=30, progress=20, crash=35)
    config.progress = 33

    restored = FitnessConfig.from_dict(config.to_dict())

    assert restored == config
    assert restored.progress == 33


def test_unknown_weight_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown"):
        FitnessConfig(weights={"unknown": 1})
