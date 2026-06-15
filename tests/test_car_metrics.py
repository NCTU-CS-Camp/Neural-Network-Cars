"""Tests for the per-run metric tracking that feeds the fitness features.

These exercise Car.track_run_metrics / reset_run_metrics in isolation (no
display or collision surface needed)."""

from game_engine.backend.car import Car


def make_car():
    return Car([6, 6, 4])


def test_track_increments_frames_alive():
    car = make_car()
    car.track_run_metrics()
    car.track_run_metrics()
    assert car.frames_alive == 2


def test_track_records_max_distance_from_spawn():
    car = make_car()
    car.reset_run_metrics()  # spawn = current (x, y)
    car.x += 30.0
    car.y += 40.0
    car.track_run_metrics()  # distance 50
    assert car.max_dist == 50.0


def test_max_distance_keeps_the_peak_when_returning():
    car = make_car()
    car.reset_run_metrics()
    car.x += 30.0
    car.y += 40.0
    car.track_run_metrics()  # distance 50
    car.x = car.spawn_x
    car.y = car.spawn_y
    car.track_run_metrics()  # distance 0, but peak stays
    assert car.max_dist == 50.0


def test_coverage_counts_unique_grid_cells():
    car = make_car()
    car.reset_run_metrics()
    car.track_run_metrics()  # cell A
    car.track_run_metrics()  # same cell A (no movement)
    car.x += 200.0
    car.track_run_metrics()  # cell B
    assert len(car.visited_cells) == 2


def test_low_speed_frames_accumulate_then_reset():
    car = make_car()
    car.reset_run_metrics()
    car.velocity = 0.0
    car.track_run_metrics()
    car.track_run_metrics()
    assert car.low_speed_frames == 2
    car.velocity = 5.0
    car.track_run_metrics()
    assert car.low_speed_frames == 0


def test_reset_state_also_resets_run_metrics():
    car = make_car()
    car.track_run_metrics()
    car.x += 100.0
    car.track_run_metrics()
    car.reset_state(200.0, 300.0)
    assert car.frames_alive == 0
    assert car.max_dist == 0.0
    assert car.visited_cells == set()
    assert car.low_speed_frames == 0
    # spawn recaptured at the new reset position
    assert car.spawn_x == 200.0
    assert car.spawn_y == 300.0


def test_reset_run_metrics_clears_counters_and_recaptures_spawn():
    car = make_car()
    car.x = 300.0
    car.y = 700.0
    car.track_run_metrics()
    car.reset_run_metrics()
    assert car.frames_alive == 0
    assert car.max_dist == 0.0
    assert car.visited_cells == set()
    assert car.low_speed_frames == 0
    assert car.spawn_x == 300.0
    assert car.spawn_y == 700.0
