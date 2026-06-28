from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StepContext:
    velocity: float
    progress_delta: float
    progress_ratio: float
    center_offset: float
    normalized_center_offset: float
    heading_alignment: float
    front_clearance: float
    min_clearance: float
    side_clearance_balance: float
    turn_amount: float
    collided: bool
    finished: bool
    is_stalled: bool
    is_spinning: bool
    frame: int
    time_elapsed: float


class FitnessStrategy:
    name = "base"

    def reset(self) -> None:
        return

    def score_step(self, context: StepContext) -> float:
        raise NotImplementedError


B = 10.0
B_CRASH = 1000.0
FINISH_BONUS = 10000.0

REWARD_BLOCKS = ("speed", "progress", "centered", "alignment", "safety")
PERSTEP_PENALTY_BLOCKS = ("stall", "spin", "wrong_way", "time")
REWARD_MAX_EFFECT = {
    "progress": 10.0,
    "speed": 1.0,
    "alignment": 3.0,
    "safety": 3.0,
    "centered": 2.0,
}
PROGRESS_RATIO_BONUS = 0.5
TIME_PENALTY_MAX_SCALE = 0.1


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(value, upper))


def _split_params(params: dict) -> tuple[dict, dict]:
    """Accept both the new {rewards, penalties} shape and a flat rewards-only dict."""
    if "rewards" in params or "penalties" in params:
        return dict(params.get("rewards", {})), dict(params.get("penalties", {}))
    return dict(params), {}


class BeginnerMix(FitnessStrategy):
    name = "beginner_mix"

    def __init__(self) -> None:
        self.rewards: dict[str, float] = {}
        self.penalties: dict[str, float] = {}

    def configure(self, params: dict) -> None:
        rewards, penalties = _split_params(params)
        self.rewards = {
            k: _clamp(float(v), 0.0, 100.0)
            for k, v in rewards.items()
            if k in REWARD_BLOCKS
        }
        self.penalties = {
            k: max(0.0, float(v))
            for k, v in penalties.items()
            if k in PERSTEP_PENALTY_BLOCKS or k == "crash"
        }

    def _reward_factors(self, c: StepContext) -> dict[str, float]:
        return {
            "speed": max(0.0, c.velocity),
            "progress": max(0.0, c.progress_delta),
            "centered": _clamp(1.0 - c.normalized_center_offset),
            "alignment": _clamp(c.heading_alignment),
            "safety": _clamp(c.min_clearance / 90.0),
        }

    def _perstep_penalty_factors(self, c: StepContext) -> dict[str, float]:
        return {
            "stall": 1.0 if c.is_stalled else 0.0,
            "spin": 1.0 if c.is_spinning else 0.0,
            "wrong_way": 1.0 if c.heading_alignment < 0.0 else 0.0,
            "time": 1.0,
        }

    def score_step(self, context: StepContext) -> float:
        factors = self._reward_factors(context)
        reward = sum(
            (self.rewards[k] / 100.0) * REWARD_MAX_EFFECT[k] * factors[k]
            for k in self.rewards
        )
        reward += _clamp(context.progress_ratio) * PROGRESS_RATIO_BONUS

        penalty = 0.0
        pfactors = self._perstep_penalty_factors(context)
        for key, weight in self.penalties.items():
            if key == "crash":
                continue
            if key == "time":
                penalty += (weight / 100.0) * TIME_PENALTY_MAX_SCALE * context.time_elapsed
            else:
                penalty += (weight / 100.0) * B * pfactors[key]

        step = reward - penalty
        if context.collided:
            step -= (self.penalties.get("crash", 0.0) / 100.0) * B_CRASH
        if context.finished:
            step += FINISH_BONUS
        return step


class SpeedOnlyBaseline(FitnessStrategy):
    name = "speed_only_baseline"

    def score_step(self, context: StepContext) -> float:
        return context.velocity


class ProgressOnly(FitnessStrategy):
    name = "progress_only"

    def score_step(self, context: StepContext) -> float:
        return context.progress_delta


class RaceMetricProxy(FitnessStrategy):
    name = "race_metric_proxy"

    def score_step(self, context: StepContext) -> float:
        time_penalty = context.time_elapsed * 0.03
        behavior_penalty = 5.0 if context.is_stalled else 0.0
        behavior_penalty += 4.0 if context.is_spinning else 0.0
        score = (
            (context.progress_delta * 6.0)
            + (context.velocity * 0.4)
            + (context.progress_ratio * 0.5)
            - time_penalty
            - behavior_penalty
        )
        if context.collided:
            score -= 700.0
        if context.finished:
            score += 10000.0
        return score


STRATEGIES: dict[str, type[FitnessStrategy]] = {
    BeginnerMix.name: BeginnerMix,
    SpeedOnlyBaseline.name: SpeedOnlyBaseline,
    ProgressOnly.name: ProgressOnly,
    RaceMetricProxy.name: RaceMetricProxy,
}


def build_strategy(strategy_type: str, params: dict | None = None) -> FitnessStrategy:
    try:
        strategy_cls = STRATEGIES[strategy_type]
    except KeyError as exc:
        raise ValueError(f"Unknown fitness strategy: {strategy_type}") from exc
    strategy = strategy_cls()
    configure = getattr(strategy, "configure", None)
    if params and callable(configure):
        configure(params)
    return strategy
