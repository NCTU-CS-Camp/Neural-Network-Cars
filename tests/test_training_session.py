from types import SimpleNamespace

from game_engine.backend.training_session import TrainingSession
from shared.contracts import RuntimeSettings


def make_session():
    return TrainingSession.from_settings(RuntimeSettings())


def car(score, **kwargs):
    return SimpleNamespace(score=score, **kwargs)


def test_select_top_cars_returns_two_highest_by_score():
    session = make_session()
    cars = [car(10), car(50), car(30), car(40)]
    top = session.select_top_cars(cars, "baseline_distance", k=2)
    assert [c.score for c in top] == [50, 40]


def test_select_top_cars_default_k_is_two():
    session = make_session()
    cars = [car(1), car(2), car(3)]
    assert len(session.select_top_cars(cars, "baseline_distance")) == 2


def test_select_top_cars_handles_ties_without_error():
    session = make_session()
    cars = [car(5), car(5), car(5)]
    top = session.select_top_cars(cars, "baseline_distance", k=2)
    assert len(top) == 2


def test_select_top_cars_returns_all_when_population_smaller_than_k():
    session = make_session()
    cars = [car(7)]
    top = session.select_top_cars(cars, "baseline_distance", k=2)
    assert top == cars


def test_select_top_cars_respects_strategy():
    session = make_session()
    # explorer ranks mainly by coverage; this car wins despite a tiny score
    big_coverage = SimpleNamespace(
        score=0, visited_cells={(i, 0) for i in range(100)}
    )
    big_score = SimpleNamespace(score=2000, visited_cells=set())
    top = session.select_top_cars([big_score, big_coverage], "explorer", k=1)
    assert top == [big_coverage]
