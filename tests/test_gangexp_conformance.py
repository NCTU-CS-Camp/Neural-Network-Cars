from __future__ import annotations

import numpy as np
import pytest

from game_engine.backend.car import Car
from game_engine.backend.settings import MAPS_DIR
from game_engine.backend.track_geometry import load_track_geometry


GANGEXP_TRACE = [
    (143.01743114854952, 449.80076106038166, 185.0, 0.2),
    (143.08689041961628, 449.40683795917676, 190.0, 0.4),
    (143.2421818466778, 448.8272824634033, 195.0, 0.6000000000000001),
    (143.51579796133834, 448.0755283667746, 200.0, 0.8),
    (143.93841622307903, 447.16922057973795, 205.0, 1.0),
]


def test_engine_car_matches_gangexp_tick_order_and_physics() -> None:
    track = load_track_geometry(
        MAPS_DIR / "kaggle_maps" / "kaggle_hard.json"
    )
    car = Car([6, 6, 4])
    car.weights = [np.zeros((6, 6)), np.zeros((4, 6))]
    car.biases = [
        np.zeros((6, 1)),
        np.array([[1.0], [-1.0], [-1.0], [1.0]]),
    ]
    car.set_track_geometry(track)
    car.reset_state(
        track.start_position[0],
        track.start_position[1],
        angle=track.start_angle,
    )

    for expected in GANGEXP_TRACE:
        car.feedforward()
        car.takeAction()
        car.update()

        assert (car.x, car.y, car.angle, car.velocity) == pytest.approx(
            expected,
            abs=1e-12,
        )
        assert car.collision() is False
