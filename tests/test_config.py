from pipeline.config import ExperimentConfig


def test_strategy_type_defaults_to_beginner_mix():
    cfg = ExperimentConfig.from_dict({"strategies": [{"name": "progress_first",
                                                      "params": {"rewards": {"progress": 50}}}]})
    s = cfg.strategies[0]
    assert s.name == "progress_first"
    assert s.strategy == "beginner_mix"
    assert s.params == {"rewards": {"progress": 50}}


def test_known_baseline_name_resolves_to_its_own_strategy():
    cfg = ExperimentConfig.from_dict({"strategies": [{"name": "speed_only_baseline"}]})
    assert cfg.strategies[0].strategy == "speed_only_baseline"


def test_explicit_strategy_field_wins():
    cfg = ExperimentConfig.from_dict({"strategies": [{"name": "weird", "strategy": "progress_only"}]})
    assert cfg.strategies[0].strategy == "progress_only"


def test_disabled_strategies_are_skipped():
    cfg = ExperimentConfig.from_dict({
        "strategies": [
            {"name": "run_me", "enabled": True},
            {"name": "skip_me", "enabled": False},
        ]
    })
    assert [strategy.name for strategy in cfg.strategies] == ["run_me"]


def test_population_workers_are_loaded():
    cfg = ExperimentConfig.from_dict({"population_workers": 8})
    assert cfg.population_workers == 8
