import warnings

import numpy as np

from game_engine.backend.geometry import sigmoid


def test_sigmoid_handles_extreme_values_without_overflow_warning() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        result = sigmoid(np.array([-1_000.0, 0.0, 1_000.0]))

    np.testing.assert_allclose(result, [0.0, 0.5, 1.0])


def test_sigmoid_supports_scalar_input() -> None:
    assert sigmoid(-1_000.0) == 0.0
