from collections.abc import Iterable

import pytest

from game_engine.backend.simulator import FrameTelemetry, Simulator
from game_engine.backend.track import TrackGeometry


class FakeCar:
    def __init__(self, center: tuple[float, float], positions: Iterable[tuple[float, float]]):
        self.center = center
        self._positions = iter(positions)
        self.angle = 180.0
        self.velocity = 1.0
        self.collided = False
        self.fitness_score = 0.0
        self.d1 = self.d2 = self.d3 = self.d4 = self.d5 = 45.0

    def refresh_track_state(self, track: TrackGeometry) -> None:
        pass

    def feedforward(self) -> None:
        pass

    def takeAction(self) -> None:
        pass

    def update(self, track: TrackGeometry) -> None:
        self.center = next(self._positions)

    def collision(self, track: TrackGeometry) -> bool:
        return False


def test_wrap_progress_and_finish_bonus_event_are_one_shot() -> None:
    track = TrackGeometry.from_centerline(
        ((0.0, 0.0), (0.0, -10.0), (10.0, -10.0), (10.0, 0.0)),
        half_width=100.0,
    )
    car = FakeCar((1.0, 0.0), [(0.0, -1.0), (0.0, -2.0)])
    simulator = Simulator(track, fps=10)
    state = simulator.reset_car(car)
    state.cumulative_progress = 39.0

    first = simulator.step(car, lambda telemetry: telemetry.progress_delta)
    second = simulator.step(car, lambda telemetry: telemetry.progress_delta)

    assert first.telemetry.progress_delta == pytest.approx(2.0)
    assert first.telemetry.progress_ratio == pytest.approx(1.0)
    assert first.telemetry.finished_now
    assert first.telemetry.time_elapsed == pytest.approx(0.1)
    assert second.telemetry.progress_delta == pytest.approx(1.0)
    assert not second.telemetry.finished_now
    assert second.training_fitness == pytest.approx(3.0)


def test_spin_requires_turn_and_negligible_forward_progress() -> None:
    track = TrackGeometry.from_centerline(
        ((0.0, 0.0), (0.0, -10.0), (10.0, -10.0), (10.0, 0.0)),
        half_width=100.0,
    )
    car = FakeCar((0.0, 0.0), [(0.0, 0.0)])

    def turn() -> None:
        car.angle += 5.0

    car.takeAction = turn  # type: ignore[method-assign]
    simulator = Simulator(track, fps=30)
    result = simulator.step(car, lambda telemetry: 0.0)

    assert result.telemetry.is_spinning
    assert isinstance(result.telemetry, FrameTelemetry)
