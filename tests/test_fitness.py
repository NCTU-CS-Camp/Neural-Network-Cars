from types import SimpleNamespace

import pytest

from GA import fitness


def car(**kwargs):
    """A duck-typed stand-in for a Car; fitness only reads attributes."""
    return SimpleNamespace(**kwargs)


# --- original strategies are preserved (raw-scored, unchanged) --------------


def test_original_baseline_distance_returns_raw_score():
    assert fitness.baseline_distance(car(score=3000.0)) == pytest.approx(3000.0)


def test_original_strategies_still_registered():
    for name in ("baseline_distance", "progress_speed", "checkpoint_progress"):
        assert name in fitness.FITNESS_STRATEGIES


# --- make_weighted: normalization ------------------------------------------


def test_make_weighted_normalizes_distance_to_one_at_reference_max():
    strat = fitness.make_weighted({"distance": 1.0})
    assert strat(car(score=3000.0)) == pytest.approx(1.0)


def test_make_weighted_scales_linearly_below_reference():
    strat = fitness.make_weighted({"distance": 1.0})
    assert strat(car(score=1500.0)) == pytest.approx(0.5)


def test_make_weighted_clamps_above_reference_max():
    strat = fitness.make_weighted({"distance": 1.0})
    assert strat(car(score=9000.0)) == pytest.approx(1.0)


def test_make_weighted_applies_weight():
    strat = fitness.make_weighted({"distance": 2.0})
    assert strat(car(score=3000.0)) == pytest.approx(2.0)


# --- make_weighted: composition --------------------------------------------


def test_make_weighted_ignores_unknown_features():
    strat = fitness.make_weighted({"distance": 1.0, "does_not_exist": 99.0})
    assert strat(car(score=3000.0)) == pytest.approx(1.0)


def test_make_weighted_sums_multiple_features():
    strat = fitness.make_weighted({"distance": 1.0, "speed": 1.0})
    assert strat(car(score=3000.0, velocity=10.0)) == pytest.approx(2.0)


def test_missing_attributes_default_to_zero():
    strat = fitness.make_weighted({"distance": 1.0, "coverage": 1.0, "speed": 1.0})
    assert strat(car()) == pytest.approx(0.0)


# --- individual feature behaviour ------------------------------------------


def test_crash_feature_is_penalty_with_negative_weight():
    strat = fitness.make_weighted({"crash": -1.0})
    assert strat(car(collided=True)) == pytest.approx(-1.0)
    assert strat(car(collided=False)) == pytest.approx(0.0)


def test_lateral_balance_penalizes_imbalance():
    strat = fitness.make_weighted({"lateral_balance": 1.0})
    assert strat(car(d4=200.0, d5=0.0)) == pytest.approx(-1.0)
    assert strat(car(d4=50.0, d5=50.0)) == pytest.approx(0.0)


def test_avg_speed_uses_frames_alive():
    strat = fitness.make_weighted({"avg_speed": 1.0})
    # score / frames = 1500 / 150 = 10 (= normalizer) -> 1.0
    assert strat(car(score=1500.0, frames_alive=150)) == pytest.approx(1.0)


def test_avg_speed_no_division_by_zero():
    strat = fitness.make_weighted({"avg_speed": 1.0})
    assert strat(car(score=0.0, frames_alive=0)) == pytest.approx(0.0)


def test_coverage_counts_visited_cells():
    strat = fitness.make_weighted({"coverage": 1.0})
    cells = {(i, 0) for i in range(200)}  # 200 = normalizer -> 1.0
    assert strat(car(visited_cells=cells)) == pytest.approx(1.0)


# --- strategy resolution ----------------------------------------------------


def test_get_fitness_strategy_custom_uses_given_weights():
    strat = fitness.get_fitness_strategy("custom", {"distance": 1.0})
    assert strat(car(score=3000.0)) == pytest.approx(1.0)


def test_get_fitness_strategy_resolves_weighted_preset():
    # explorer = {"coverage": 1.0, "distance": 0.3}
    strat = fitness.get_fitness_strategy("explorer")
    cells = {(i, 0) for i in range(200)}  # coverage -> 1.0
    assert strat(car(visited_cells=cells, score=0.0)) == pytest.approx(1.0)


def test_get_fitness_strategy_resolves_original_function():
    # original strategies stay raw-scored, not normalized
    strat = fitness.get_fitness_strategy("baseline_distance")
    assert strat(car(score=3000.0)) == pytest.approx(3000.0)


def test_get_fitness_strategy_unknown_falls_back_to_baseline():
    strat = fitness.get_fitness_strategy("nope_not_real")
    assert strat(car(score=3000.0)) == pytest.approx(3000.0)


def test_get_fitness_strategy_custom_without_weights_falls_back():
    strat = fitness.get_fitness_strategy("custom", None)
    assert strat(car(score=3000.0)) == pytest.approx(3000.0)


def test_score_population_maps_strategy_over_cars():
    cars = [car(score=3000.0), car(score=1500.0)]
    scores = fitness.score_population(cars, "baseline_distance")
    assert scores == [pytest.approx(3000.0), pytest.approx(1500.0)]


# --- registries / discoverability (used by UI to build controls) -----------


def test_list_strategies_includes_original_and_weighted():
    names = fitness.list_strategies()
    assert "baseline_distance" in names  # original
    assert "explorer" in names  # new weighted preset


def test_list_features_includes_core_features():
    features = fitness.list_features()
    for name in ("distance", "speed", "coverage", "crash"):
        assert name in features
