from __future__ import annotations

from typing import Callable


FitnessStrategy = Callable[[object], float]


def baseline_distance(car: object) -> float:
    return float(getattr(car, "score", 0.0))


def progress_speed(car: object) -> float:
    score = float(getattr(car, "score", 0.0))
    velocity = float(getattr(car, "velocity", 0.0))
    collided = bool(getattr(car, "collided", False))
    return score + (velocity * 5.0) - (25.0 if collided else 0.0)


def checkpoint_progress(car: object) -> float:
    score = float(getattr(car, "score", 0.0))
    velocity = float(getattr(car, "velocity", 0.0))
    d1 = float(getattr(car, "d1", 0.0))
    d2 = float(getattr(car, "d2", 0.0))
    d3 = float(getattr(car, "d3", 0.0))
    sensor_balance = min(d1, d2 + d3)
    stalled = velocity < 0.5
    return score + sensor_balance - (50.0 if stalled else 0.0)


FITNESS_STRATEGIES: dict[str, FitnessStrategy] = {
    "baseline_distance": baseline_distance,
    "progress_speed": progress_speed,
    "checkpoint_progress": checkpoint_progress,
}


# --------------------------------------------------------------------------- #
# Configurable feature + weight system
#
# Sits alongside the hand-written strategies above. A "weighted" strategy is a
# named vector of feature weights; each feature is normalised into roughly
# [-1, 1] before weighting, so a weight reads as relative importance and a
# player can tune their own mix. Add a feature by registering an extractor in
# FEATURES; add a strategy by adding a line to WEIGHTED_PRESETS.
# --------------------------------------------------------------------------- #
FeatureExtractor = Callable[[object], float]


def _distance(car: object) -> float:
    return float(getattr(car, "score", 0.0))


def _speed(car: object) -> float:
    return float(getattr(car, "velocity", 0.0))


def _avg_speed(car: object) -> float:
    frames = float(getattr(car, "frames_alive", 0.0))
    return float(getattr(car, "score", 0.0)) / max(frames, 1.0)


def _front_clearance(car: object) -> float:
    return float(getattr(car, "d1", 0.0))


def _lateral_balance(car: object) -> float:
    # Negative magnitude: a perfectly centred car (d4 == d5) scores 0, hugging
    # a wall scores negative. Pair with a positive weight.
    return -abs(float(getattr(car, "d4", 0.0)) - float(getattr(car, "d5", 0.0)))


def _diag_balance(car: object) -> float:
    return -abs(float(getattr(car, "d2", 0.0)) - float(getattr(car, "d3", 0.0)))


def _coverage(car: object) -> float:
    return float(len(getattr(car, "visited_cells", ()) or ()))


def _survival(car: object) -> float:
    return float(getattr(car, "frames_alive", 0.0))


def _reach(car: object) -> float:
    return float(getattr(car, "max_dist", 0.0))


def _crash(car: object) -> float:
    return 1.0 if getattr(car, "collided", False) else 0.0


def _stall(car: object) -> float:
    return 1.0 if float(getattr(car, "low_speed_frames", 0.0)) > 60 else 0.0


FEATURES: dict[str, FeatureExtractor] = {
    "distance": _distance,
    "speed": _speed,
    "avg_speed": _avg_speed,
    "front_clearance": _front_clearance,
    "lateral_balance": _lateral_balance,
    "diag_balance": _diag_balance,
    "coverage": _coverage,
    "survival": _survival,
    "reach": _reach,
    "crash": _crash,
    "stall": _stall,
}


# Reference maxima used to normalise each feature into roughly [-1, 1]. Tune
# per track if needed.
NORMALIZERS: dict[str, float] = {
    "distance": 3000.0,
    "speed": 10.0,
    "avg_speed": 10.0,
    "front_clearance": 200.0,
    "lateral_balance": 200.0,
    "diag_balance": 200.0,
    "coverage": 200.0,
    "survival": 1500.0,
    "reach": 1000.0,
    "crash": 1.0,
    "stall": 1.0,
}


# New configurable strategies (distinct names from the originals above).
WEIGHTED_PRESETS: dict[str, dict[str, float]] = {
    "fast_and_safe": {"distance": 1.0, "speed": 0.5, "crash": -1.0},
    "explorer": {"coverage": 1.0, "distance": 0.3},
    "smooth_racer": {
        "distance": 1.0,
        "front_clearance": 0.5,
        "lateral_balance": 0.5,
        "crash": -0.5,
    },
    "speed_demon": {"avg_speed": 1.0, "survival": 0.3, "crash": -0.8},
    "survivor": {"survival": 1.0, "distance": 0.3, "crash": -1.0},
}


def _normalize(name: str, raw: float) -> float:
    norm = raw / NORMALIZERS.get(name, 1.0)
    return max(-1.0, min(1.0, norm))


def make_weighted(weights: dict[str, float]) -> FitnessStrategy:
    """Build a fitness strategy from a {feature_name: weight} mapping."""

    def strategy(car: object) -> float:
        total = 0.0
        for name, weight in weights.items():
            extractor = FEATURES.get(name)
            if extractor is None:
                continue
            total += weight * _normalize(name, extractor(car))
        return total

    return strategy


def get_fitness_strategy(
    name: str, custom_weights: dict[str, float] | None = None
) -> FitnessStrategy:
    """Resolve a strategy by name.

    Order: a player ``"custom"`` weighting, then the original hand-written
    strategies, then the weighted presets; anything unknown falls back to
    ``baseline_distance``.
    """
    if name == "custom" and custom_weights:
        return make_weighted(custom_weights)
    if name in FITNESS_STRATEGIES:
        return FITNESS_STRATEGIES[name]
    if name in WEIGHTED_PRESETS:
        return make_weighted(WEIGHTED_PRESETS[name])
    return baseline_distance


def score_population(
    population: list[object],
    strategy_name: str,
    custom_weights: dict[str, float] | None = None,
) -> list[float]:
    strategy = get_fitness_strategy(strategy_name, custom_weights)
    return [strategy(car) for car in population]


def list_strategies() -> list[str]:
    """All selectable strategy names (originals + weighted presets)."""
    return list(FITNESS_STRATEGIES) + list(WEIGHTED_PRESETS)


def list_features() -> list[str]:
    """Feature names, e.g. for auto-generating custom-weight sliders."""
    return list(FEATURES)

