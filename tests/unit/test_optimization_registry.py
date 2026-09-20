from pathlib import Path

from optimization.registry import ExperimentRecord, OptimizationRegistry


def _record(**overrides) -> ExperimentRecord:
    base = dict(
        strategy="classic_sr_trend_fib", symbol="EURUSD", timeframe="M15", dataset="mt5_2025_2026",
        phase="train", training_period=("2025-09-15", "2026-03-15"), validation_period=("2026-03-15", "2026-06-15"),
        oos_period=("2026-06-15", "2026-09-16"), parameters={}, component_weights={"trend_strength": 0.5, "fibonacci": 0.5},
        disabled_components=[], trade_count=100, resolved_count=95, win_rate=0.2, tp1_rate=0.15, tp2_rate=0.05,
        sl_rate=0.8, profit_factor=1.1, net_r=5.0, expectancy=0.05, average_r=0.05, max_drawdown_r=3.0,
        instability=0.1, composite_objective=0.42, status="Candidate",
    )
    base.update(overrides)
    return ExperimentRecord(**base)


def test_log_and_read_back_a_single_experiment(tmp_path: Path):
    registry = OptimizationRegistry(path=tmp_path / "experiments.jsonl")
    registry.log(_record())

    records = registry.all()

    assert len(records) == 1
    assert records[0]["strategy"] == "classic_sr_trend_fib"
    assert records[0]["status"] == "Candidate"


def test_registry_is_append_only_across_instances(tmp_path: Path):
    path = tmp_path / "experiments.jsonl"
    OptimizationRegistry(path=path).log(_record(status="Rejected"))
    OptimizationRegistry(path=path).log(_record(status="Robust Candidate"))

    records = OptimizationRegistry(path=path).all()

    assert len(records) == 2
    assert {r["status"] for r in records} == {"Rejected", "Robust Candidate"}


def test_for_strategy_filters_correctly(tmp_path: Path):
    registry = OptimizationRegistry(path=tmp_path / "experiments.jsonl")
    registry.log(_record(strategy="classic_sr_trend_fib"))
    registry.log(_record(strategy="smc_structure_ob_fvg"))

    classic_only = registry.for_strategy("classic_sr_trend_fib")

    assert len(classic_only) == 1
    assert classic_only[0]["strategy"] == "classic_sr_trend_fib"


def test_empty_registry_returns_empty_list(tmp_path: Path):
    registry = OptimizationRegistry(path=tmp_path / "does_not_exist.jsonl")
    assert registry.all() == []
