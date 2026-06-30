import numpy as np
import pygame
import pytest

import game_engine.backend.car as car_module
from game_engine.backend.car import Car


LAYER_SIZES = [2, 3, 1]


def _assert_same_parameters(first: Car, second: Car) -> None:
    for first_layer, second_layer in zip(
        first.biases + first.weights,
        second.biases + second.weights,
        strict=True,
    ):
        np.testing.assert_array_equal(first_layer, second_layer)


def test_same_mlp_init_seed_creates_same_parameters() -> None:
    first = Car(LAYER_SIZES, mlp_init_seed=123)
    second = Car(LAYER_SIZES, mlp_init_seed=123)

    assert first.mlp_init_seed == 123
    _assert_same_parameters(first, second)


def test_default_mlp_init_seed_is_3057() -> None:
    default_car = Car(LAYER_SIZES)
    explicit_car = Car(LAYER_SIZES, mlp_init_seed=3057)

    assert default_car.mlp_init_seed == 3057
    _assert_same_parameters(default_car, explicit_car)


def test_setting_mlp_init_seed_reinitializes_parameters() -> None:
    car = Car(LAYER_SIZES)

    car.mlp_init_seed = 456

    _assert_same_parameters(car, Car(LAYER_SIZES, mlp_init_seed=456))


def test_seed_3057_uses_documented_weight_then_bias_draw_order() -> None:
    car = Car([6, 6, 4], mlp_init_seed=3057)

    np.testing.assert_allclose(
        car.weights[0][0],
        [-2.0334, 0.2190, 0.3928, 0.3206, -0.7062, 1.8629],
        atol=5e-5,
    )
    np.testing.assert_allclose(
        car.weights[1][0],
        [-1.0838, -0.2596, -0.5760, 1.2499, 0.0351, -0.9405],
        atol=5e-5,
    )
    np.testing.assert_allclose(
        car.biases[0][:, 0],
        [0.9080, 0.3684, 1.2689, -0.4436, 0.9769, -0.7031],
        atol=5e-5,
    )
    np.testing.assert_allclose(
        car.biases[1][:, 0],
        [-0.0299, -1.4701, 0.2650, 1.0101],
        atol=5e-5,
    )


def test_population_cars_continue_from_one_shared_rng() -> None:
    shared_rng = np.random.default_rng(3057)
    first = Car(LAYER_SIZES, mlp_init_rng=shared_rng)
    second = Car(LAYER_SIZES, mlp_init_rng=shared_rng)

    reference_rng = np.random.default_rng(3057)
    expected_first = Car(LAYER_SIZES, mlp_init_rng=reference_rng)
    expected_second = Car(LAYER_SIZES, mlp_init_rng=reference_rng)

    assert first.mlp_init_seed == 3057
    assert second.mlp_init_seed == 3057
    _assert_same_parameters(first, expected_first)
    _assert_same_parameters(second, expected_second)
    assert any(
        not np.array_equal(first_layer, second_layer)
        for first_layer, second_layer in zip(
            first.weights + first.biases,
            second.weights + second.biases,
            strict=True,
        )
    )


def test_shared_rng_keeps_seed_as_reproducibility_metadata() -> None:
    car = Car(
        LAYER_SIZES,
        mlp_init_seed=123,
        mlp_init_rng=np.random.default_rng(3057),
    )

    assert car.mlp_init_seed == 123


@pytest.mark.parametrize("seed", [True, 1.5, "123"])
def test_mlp_init_seed_rejects_non_integers(seed: object) -> None:
    with pytest.raises(TypeError, match="integer or None"):
        Car(LAYER_SIZES, mlp_init_seed=seed)  # type: ignore[arg-type]


def test_mlp_init_seed_rejects_negative_values() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        Car(LAYER_SIZES, mlp_init_seed=-1)


def test_sensor_and_collision_checks_prefer_collision_surface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    surface = pygame.Surface((220, 220), flags=pygame.SRCALPHA)
    surface.fill((255, 255, 255, 255))
    monkeypatch.setattr(car_module, "collision_surface", surface)

    class UnexpectedGeometryCheck:
        def contains(self, point: tuple[float, float]) -> bool:
            raise AssertionError("geometry should not be used when a bitmap is loaded")

    car = Car(LAYER_SIZES, mlp_init_seed=123)
    car.reset_state(110, 110)
    track = UnexpectedGeometryCheck()

    car.refresh_track_state(track)  # type: ignore[arg-type]

    assert not car.collision(track)  # type: ignore[arg-type]
    assert min(car.d1, car.d2, car.d3, car.d4, car.d5) > 0


def test_sensor_and_collision_checks_fall_back_to_geometry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(car_module, "collision_surface", None)

    class CircularTrack:
        calls = 0

        def contains(self, point: tuple[float, float]) -> bool:
            self.calls += 1
            dx = point[0] - 110
            dy = point[1] - 110
            return (dx * dx) + (dy * dy) <= 100 * 100

    car = Car(LAYER_SIZES, mlp_init_seed=123)
    car.reset_state(110, 110)
    track = CircularTrack()

    car.refresh_track_state(track)  # type: ignore[arg-type]

    assert not car.collision(track)  # type: ignore[arg-type]
    assert track.calls > 0
