from game_engine.backend.competition_track import CompetitionRunTracker


def _vertical_gate(index: int, x: float) -> dict:
    return {
        "index": index,
        "center": [x, 0.0],
        "a": [x, -5.0],
        "b": [x, 5.0],
    }


def test_tracker_completes_only_after_checkpoints_are_crossed_in_order() -> None:
    tracker = CompetitionRunTracker(
        checkpoints=(
            _vertical_gate(0, 10.0),
            _vertical_gate(1, 100.0),
        ),
        total_length_px=100.0,
    )

    tracker.advance((0.0, 0.0), (11.0, 0.0), tick=1)
    tracker.advance((91.0, 0.0), (101.0, 0.0), tick=2)

    assert tracker.completed
    assert tracker.lap_ticks == 2


def test_reverse_checkpoint_order_does_not_complete_lap() -> None:
    tracker = CompetitionRunTracker(
        checkpoints=(
            _vertical_gate(0, 10.0),
            _vertical_gate(1, 100.0),
        ),
        total_length_px=100.0,
    )

    previous = (101.0, 0.0)
    for tick, x in enumerate(range(91, 0, -10), start=1):
        current = (float(x), 0.0)
        tracker.advance(previous, current, tick=tick)
        previous = current

    assert not tracker.completed
    assert tracker.checkpoints_completed == 1
