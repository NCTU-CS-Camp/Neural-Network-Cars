from __future__ import annotations

from pipeline.fitness import BeginnerMix, FINISH_BONUS, B_CRASH
from pipeline.simulator import StepContext


def ctx(**overrides) -> StepContext:
    base = dict(
        velocity=0.0,
        progress_delta=0.0,
        progress_ratio=0.0,
        center_offset=0.0,
        normalized_center_offset=0.0,
        heading_alignment=1.0,
        front_clearance=100.0,
        min_clearance=100.0,
        side_clearance_balance=0.0,
        turn_amount=0.0,
        collided=False,
        finished=False,
        is_stalled=False,
        is_spinning=False,
        frame=30,
        time_elapsed=1.0,  # dt = time_elapsed / frame = 1/30
    )
    base.update(overrides)
    return StepContext(**base)


def test_flat_dict_is_treated_as_rewards():
    strat = BeginnerMix()
    strat.configure({"speed": 30, "progress": 40, "centered": 10, "alignment": 10, "safety": 10})
    assert strat.rewards == {"speed": 30.0, "progress": 40.0, "centered": 10.0,
                             "alignment": 10.0, "safety": 10.0}
    assert strat.penalties == {}


def test_rewards_are_0_to_100_sliders_mapped_to_per_block_effects():
    strat = BeginnerMix()
    strat.configure({"rewards": {"progress": 60, "speed": 40}})
    step = strat.score_step(ctx(progress_delta=1.0, velocity=10.0))
    assert step == 10.0


def test_penalty_at_100_subtracts_full_penalty_block_for_that_frame():
    strat = BeginnerMix()
    strat.configure({"rewards": {"progress": 60}, "penalties": {"stall": 100}})
    step = strat.score_step(ctx(progress_delta=1.0, is_stalled=True))
    assert step == -4.0


def test_extra_reward_blocks_add_instead_of_diluting_existing_rewards():
    a = BeginnerMix(); a.configure({"rewards": {"progress": 60}})
    b = BeginnerMix(); b.configure({"rewards": {"progress": 60, "speed": 40}})
    c = ctx(progress_delta=1.0, velocity=10.0)
    assert b.score_step(c) == a.score_step(c) + 4.0


def test_progress_uses_raw_delta_instead_of_normalized_score():
    strat = BeginnerMix(); strat.configure({"rewards": {"progress": 60}})
    assert strat.score_step(ctx(progress_delta=10.0)) == 60.0


def test_speed_uses_raw_velocity_instead_of_normalized_score():
    strat = BeginnerMix(); strat.configure({"rewards": {"speed": 40}})
    assert strat.score_step(ctx(velocity=10.0)) == 4.0


def test_handling_rewards_have_stronger_max_effects():
    strat = BeginnerMix()
    strat.configure({"rewards": {"alignment": 100, "safety": 50, "centered": 20}})
    step = strat.score_step(
        ctx(
            heading_alignment=1.0,
            min_clearance=90.0,
            normalized_center_offset=0.0,
        )
    )
    assert step == 4.9


def test_progress_ratio_bonus_is_built_in():
    strat = BeginnerMix(); strat.configure({})
    assert strat.score_step(ctx(progress_ratio=0.5)) == 0.25


def test_time_penalty_scales_with_elapsed_time_and_slider():
    strat = BeginnerMix()
    strat.configure({"penalties": {"time": 30}})
    assert strat.score_step(ctx(time_elapsed=10.0)) == -0.3


def test_time_penalty_100_percent_uses_0_1_scale():
    strat = BeginnerMix()
    strat.configure({"penalties": {"time": 100}})
    assert strat.score_step(ctx(time_elapsed=10.0)) == -1.0


def test_crash_is_one_shot_and_independent_of_dt():
    strat = BeginnerMix(); strat.configure({"penalties": {"crash": 100}})
    c30 = ctx(collided=True, frame=30, time_elapsed=1.0)
    c60 = ctx(collided=True, frame=60, time_elapsed=1.0)
    assert strat.score_step(c30) == strat.score_step(c60) == -B_CRASH


def test_finish_adds_fixed_bonus():
    strat = BeginnerMix(); strat.configure({})
    assert strat.score_step(ctx(finished=True)) == FINISH_BONUS


def test_negative_penalty_is_clamped_to_zero():
    strat = BeginnerMix(); strat.configure({"penalties": {"stall": -50}})
    assert strat.penalties["stall"] == 0.0


def test_reward_sliders_are_clamped_to_0_to_100():
    strat = BeginnerMix(); strat.configure({"rewards": {"progress": 150, "speed": -20}})
    assert strat.rewards == {"progress": 100.0, "speed": 0.0}
