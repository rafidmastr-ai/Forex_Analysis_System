"""Task-36 driver: independent, per-strategy weight optimization against the
real MT5-derived data (see optimization/ for the underlying framework).

Run ONE strategy per invocation — Classic, then SMC, then ICT are never
mixed together in a single search, per the spec ("do we know Classic
improved because of ITS weights?"):

    python scripts/optimize_strategy.py classic
    python scripts/optimize_strategy.py smc
    python scripts/optimize_strategy.py ict
    python scripts/optimize_strategy.py sweep_displacement
    python scripts/optimize_strategy.py session_breakout

Design choices made once, up front, and held fixed across every experiment
in this run (never tuned post-hoc after seeing results — that would be
threshold/data shopping):

  * min_confidence=65 for every backtest in this script. Confidence does
    NOT gate trades in production /analyze (see backtesting/engine.py's
    doc comment on `min_confidence`) — without some filter, different
    component weights would relabel the exact same set of trades and could
    never change a single performance number. 65 sits roughly in the top
    third (Classic: achievable range 55-70) to top half (SMC/ICT: 55-75)
    of each strategy's achievable confidence range.
  * "Baseline" in this script's output means DEFAULT_WEIGHTS evaluated
    under this SAME min_confidence=65 filter — not the unfiltered
    production numbers in data/historical_backtest_results/baseline_results
    .json, which is never altered by this work. This isolates "did the
    weight choice help" from "did adding a confidence filter help" (a
    different, real, but separate question) by holding the filter fixed
    across the whole comparison.
  * EURUSD is the primary optimization symbol (full search + validation +
    OOS + robustness + ablation). XAUUSD is a generalization CHECK ONLY:
    the EURUSD-derived candidate's weights are evaluated as-is on XAUUSD's
    own Train/Validation/OOS split, with no re-search — this is what the
    acceptance rule's "must not depend on only one Symbol" needs, without
    turning this into a second, mixed, EURUSD+XAUUSD search.

Every single evaluation (including the ones that get rejected) is appended
to the Optimization Registry (data/optimization_registry/experiments.jsonl,
gitignored like all of data/ — nothing is silently discarded). A compact,
structured summary of the whole run for this strategy is additionally
written to data/optimization_results/<strategy>_summary.json for the final
report (Task 39).

Known data limitation, documented rather than hidden: EURUSD_H4.csv ends
2026-08-27, about 3 weeks before EURUSD_M15.csv's 2026-09-16 end — so the
last ~3 weeks of the EURUSD Out-of-Sample window run with a stale (but
present, never crashing) "higher timeframe" context via CandleSeries
.sliced_as_of's normal point-in-time behavior.
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from adapters.historical_file.file_adapter import HistoricalFileMarketDataProvider  # noqa: E402
from core.confidence.component_scoring import ComponentWeights  # noqa: E402
from core.confidence.confidence_engine import ConfidenceEngine  # noqa: E402
from core.market_data.models import Symbol, Timeframe  # noqa: E402
from core.selection.strategy_selection_engine import StrategySelectionEngine  # noqa: E402
from core.strategies.classic.classic_strategy import (  # noqa: E402
    GATE_CANDLESTICK,
    GATE_SUPPORT_RESISTANCE,
    ClassicStrategy,
)
from core.strategies.ict.ict_strategy import (  # noqa: E402
    GATE_DISPLACEMENT as ICT_GATE_DISPLACEMENT,
)
from core.strategies.ict.ict_strategy import (
    GATE_ENTRY_ZONE as ICT_GATE_ENTRY_ZONE,
)
from core.strategies.ict.ict_strategy import (
    GATE_KILL_ZONE,
    ICTStrategy,
)
from core.strategies.ict.ict_strategy import (
    GATE_PREMIUM_DISCOUNT as ICT_GATE_PREMIUM_DISCOUNT,
)
from core.strategies.session_breakout.session_breakout_strategy import (
    GATE_DISPLACEMENT as SB_GATE_DISPLACEMENT,
)
from core.strategies.session_breakout.session_breakout_strategy import (
    GATE_SESSION_WINDOW,
    SessionBreakoutStrategy,
)
from core.strategies.smc.smc_strategy import (
    GATE_DISPLACEMENT as SMC_GATE_DISPLACEMENT,
)
from core.strategies.smc.smc_strategy import (
    GATE_ENTRY_ZONE as SMC_GATE_ENTRY_ZONE,
)
from core.strategies.smc.smc_strategy import (
    GATE_ORDER_BLOCK,
    SMCStrategy,
)
from core.strategies.smc.smc_strategy import (
    GATE_PREMIUM_DISCOUNT as SMC_GATE_PREMIUM_DISCOUNT,
)
from core.strategies.sweep_displacement.sweep_displacement_strategy import (
    GATE_DISPLACEMENT as SD_GATE_DISPLACEMENT,
)
from core.strategies.sweep_displacement.sweep_displacement_strategy import (
    GATE_ENTRY_ZONE as SD_GATE_ENTRY_ZONE,
)
from core.strategies.sweep_displacement.sweep_displacement_strategy import (
    GATE_PREMIUM_DISCOUNT as SD_GATE_PREMIUM_DISCOUNT,
)
from core.strategies.sweep_displacement.sweep_displacement_strategy import (
    SweepDisplacementStrategy,
)
from optimization.data_split import DataSplit, chronological_split
from optimization.objective import PerformanceMetrics, composite_objective
from optimization.registry import ExperimentRecord, OptimizationRegistry
from optimization.runner import evaluate_metrics
from optimization.weight_search import random_search
from scripts.data_window import full_window_for

MIN_CONFIDENCE = 65
PERTURBATION_FRACTIONS = [0.05, 0.10, 0.15]  # how much weight to redistribute, tested at each step
TOP_K_TO_VALIDATE = 3
# NOT "mt5_2025_2026" -- that labeled the earlier MT5-export dataset, which
# no longer exists in this repository (see data/market/ and
# scripts/build_m1_historical_data.py for the current, only data source).
DATASET = "m1_ohlc_2025_2026"

# No hard-coded window here: each symbol's actual available range is
# detected from its own uploaded CSV by scripts/build_m1_historical_data.py
# and read back per-symbol via scripts.data_window.full_window_for() at each
# call site below -- the single authoritative source (see that module's
# docstring), never duplicated or assumed identical across symbols.

SYMBOLS = {
    "EURUSD": Symbol(name="EURUSD", pip_size=0.0001, digits=5, contract_size=100000),
    "XAUUSD": Symbol(name="XAUUSD", pip_size=0.01, digits=2, contract_size=100),
    "GBPUSD": Symbol(name="GBPUSD", pip_size=0.0001, digits=5, contract_size=100000),
    "NZDUSD": Symbol(name="NZDUSD", pip_size=0.0001, digits=5, contract_size=100000),
}

# Loaded from config/settings.backtest.yaml's `timeframes:` section -- the
# single, documented-in-configuration source (see that file's comments and
# core/context/timeframe_selector.py) -- rather than a second, Python-typed
# copy of the same mapping that could silently drift from it.
TIMEFRAMES_CONFIG = yaml.safe_load(Path("config/settings.backtest.yaml").read_text())["timeframes"]
LOOKBACK_BARS = {"higher": 200, "middle": 300, "entry": 500}

STRATEGY_SPECS = {
    "classic": {
        "cls": ClassicStrategy,
        "components": ["trend_strength", "fibonacci", "sr_quality", "candlestick_strength"],
        "gates": {"support_resistance_gate": GATE_SUPPORT_RESISTANCE, "candlestick_gate": GATE_CANDLESTICK},
        "n_random_samples": 16,
    },
    "smc": {
        "cls": SMCStrategy,
        "components": ["fvg", "liquidity_sweep", "structure_strength", "premium_discount_depth", "order_block_quality"],
        "gates": {
            "displacement_gate": SMC_GATE_DISPLACEMENT,
            "order_block_gate": GATE_ORDER_BLOCK,
            "entry_zone_gate": SMC_GATE_ENTRY_ZONE,
            "premium_discount_gate": SMC_GATE_PREMIUM_DISCOUNT,
        },
        "n_random_samples": 18,
    },
    "ict": {
        "cls": ICTStrategy,
        "components": ["fvg", "breaker_block", "structure_strength", "premium_discount_depth", "ote_depth"],
        "gates": {
            "kill_zone_gate": GATE_KILL_ZONE,
            "displacement_gate": ICT_GATE_DISPLACEMENT,
            "entry_zone_gate": ICT_GATE_ENTRY_ZONE,
            "premium_discount_gate": ICT_GATE_PREMIUM_DISCOUNT,
        },
        "n_random_samples": 18,
    },
    "sweep_displacement": {
        "cls": SweepDisplacementStrategy,
        "components": ["sweep_quality", "displacement_strength", "retracement_depth", "premium_discount_depth"],
        "gates": {
            "displacement_gate": SD_GATE_DISPLACEMENT,
            "entry_zone_gate": SD_GATE_ENTRY_ZONE,
            "premium_discount_gate": SD_GATE_PREMIUM_DISCOUNT,
        },
        "n_random_samples": 16,
    },
    "session_breakout": {
        "cls": SessionBreakoutStrategy,
        "components": ["range_quality", "breakout_strength", "displacement_strength", "session_timing"],
        "gates": {
            "session_window_gate": GATE_SESSION_WINDOW,
            "displacement_gate": SB_GATE_DISPLACEMENT,
        },
        "n_random_samples": 16,
    },
}


def _provider() -> HistoricalFileMarketDataProvider:
    return HistoricalFileMarketDataProvider(data_dir=Path("data/historical"), symbols=SYMBOLS)


def _selection_engine() -> StrategySelectionEngine:
    confidence_engine = ConfidenceEngine(thresholds={"weak_max": 49, "medium_max": 74}, multi_strategy_agreement_bonus=10)
    return StrategySelectionEngine(confidence_engine=confidence_engine, filters=[], min_risk_reward=1.5)


def evaluate(strategy, symbol_name: str, start: datetime, end: datetime) -> PerformanceMetrics:
    return evaluate_metrics(
        strategies=[strategy], provider=_provider(), selection_engine=_selection_engine(),
        symbol_name=symbol_name, timeframe=Timeframe.M15, start=start, end=end,
        timeframes_config=TIMEFRAMES_CONFIG, lookback_bars=LOOKBACK_BARS, min_confidence=MIN_CONFIDENCE,
    )


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _period_strs(split: DataSplit) -> dict[str, tuple[str, str]]:
    return {
        "training_period": (_iso(split.train[0]), _iso(split.train[1])),
        "validation_period": (_iso(split.validation[0]), _iso(split.validation[1])),
        "oos_period": (_iso(split.out_of_sample[0]), _iso(split.out_of_sample[1])),
    }


def _record(
    registry: OptimizationRegistry, strategy_id: str, symbol: str, split: DataSplit, phase: str,
    weights: ComponentWeights, disabled: list[str], metrics: PerformanceMetrics, status: str, notes: str = "",
) -> ExperimentRecord:
    objective = composite_objective(metrics)
    rec = ExperimentRecord(
        strategy=strategy_id, symbol=symbol, timeframe="M15", dataset=DATASET, phase=phase,
        **_period_strs(split), parameters={"min_confidence": MIN_CONFIDENCE},
        component_weights=dict(weights.weights), disabled_components=list(disabled),
        trade_count=metrics.trade_count, resolved_count=metrics.resolved_count, win_rate=metrics.win_rate,
        tp1_rate=metrics.tp1_rate, tp2_rate=metrics.tp2_rate, sl_rate=metrics.sl_rate,
        profit_factor=metrics.profit_factor if metrics.profit_factor != float("inf") else 999.0,
        net_r=metrics.net_r, expectancy=metrics.expectancy, average_r=metrics.average_r,
        max_drawdown_r=metrics.max_drawdown_r, instability=metrics.instability,
        composite_objective=objective, status=status, notes=notes,
    )
    registry.log(rec)
    return rec


def run(strategy_key: str) -> dict:
    spec = STRATEGY_SPECS[strategy_key]
    strategy_cls = spec["cls"]
    components = spec["components"]
    gates = spec["gates"]
    strategy_id = strategy_cls.strategy_id
    registry = OptimizationRegistry()

    t0 = time.time()
    print(f"=== {strategy_id} :: EURUSD split ===", flush=True)
    split = chronological_split(*full_window_for("EURUSD"))
    print(f"train={split.train} validation={split.validation} oos={split.out_of_sample}", flush=True)

    # --- Baseline (DEFAULT_WEIGHTS, same min_confidence filter as everything else) ---
    default_weights = strategy_cls.DEFAULT_WEIGHTS
    baseline_metrics = {}
    for phase, (start, end) in (("train", split.train), ("validation", split.validation), ("out_of_sample", split.out_of_sample)):
        m = evaluate(strategy_cls(weights=default_weights), "EURUSD", start, end)
        baseline_metrics[phase] = m
        _record(registry, strategy_id, "EURUSD", split, phase, default_weights, [], m, "Baseline")
        print(f"[baseline/{phase}] resolved={m.resolved_count} net_r={m.net_r:.2f} obj={composite_objective(m):.3f}", flush=True)

    # --- Weight search on TRAIN only ---
    print(f"=== weight search: {spec['n_random_samples']} samples on TRAIN ===", flush=True)

    def train_eval(weights: ComponentWeights) -> PerformanceMetrics:
        return evaluate(strategy_cls(weights=weights), "EURUSD", *split.train)

    search_results = random_search(components, train_eval, composite_objective, n_samples=spec["n_random_samples"], seed=20260920)
    for r in search_results:
        _record(registry, strategy_id, "EURUSD", split, "train", r.weights, [], r.metrics, "Candidate")
    print(f"top TRAIN objective={search_results[0].objective:.3f} weights={search_results[0].weights.weights}", flush=True)

    # --- Validate top-K TRAIN candidates ---
    print(f"=== validating top {TOP_K_TO_VALIDATE} TRAIN candidates ===", flush=True)
    validation_scored = []
    for r in search_results[:TOP_K_TO_VALIDATE]:
        vm = evaluate(strategy_cls(weights=r.weights), "EURUSD", *split.validation)
        vobj = composite_objective(vm)
        _record(registry, strategy_id, "EURUSD", split, "validation", r.weights, [], vm, "Candidate")
        validation_scored.append((vobj, r.weights, vm, r.objective))
        print(f"  train_obj={r.objective:.3f} -> validation_obj={vobj:.3f} weights={r.weights.weights}", flush=True)

    validation_scored.sort(key=lambda t: t[0], reverse=True)
    chosen_val_obj, chosen_weights, chosen_val_metrics, chosen_train_obj = validation_scored[0]
    print(f"chosen candidate: train_obj={chosen_train_obj:.3f} validation_obj={chosen_val_obj:.3f} weights={chosen_weights.weights}", flush=True)

    # --- Out-of-sample ---
    oos_metrics = evaluate(strategy_cls(weights=chosen_weights), "EURUSD", *split.out_of_sample)
    oos_obj = composite_objective(oos_metrics)
    _record(registry, strategy_id, "EURUSD", split, "out_of_sample", chosen_weights, [], oos_metrics, "Candidate")
    print(f"[candidate/oos] resolved={oos_metrics.resolved_count} net_r={oos_metrics.net_r:.2f} obj={oos_obj:.3f}", flush=True)

    # --- Robustness / perturbation (on VALIDATION) ---
    # Uses ComponentWeights.perturbed_toward() (weight REDISTRIBUTION), not
    # .perturbed() (weight RESCALING): weighted_score() renormalizes over
    # active components, so rescaling the only nonzero weight of a pure-
    # vertex candidate and renormalizing is a mathematical no-op (always
    # returns to the same normalized weight) -- found while running this
    # exact script on session_breakout's candidate, which landed on a pure
    # vertex. Redistribution moves real weight onto every OTHER component
    # (including ones currently at zero), which is a genuine test of
    # whether the candidate's shape is stable, for vertex and non-vertex
    # candidates alike. See core/confidence/component_scoring.py's
    # docstrings and research/STRATEGY_RESEARCH_REGISTRY.md for the story.
    print("=== perturbation robustness (on VALIDATION) ===", flush=True)
    perturbation_objs = []
    donors = [name for name, w in chosen_weights.weights.items() if w > 0]
    for donor in donors:
        for receiver in components:
            if receiver == donor:
                continue
            for fraction in PERTURBATION_FRACTIONS:
                pw = chosen_weights.perturbed_toward(donor, receiver, fraction)
                pm = evaluate(strategy_cls(weights=pw), "EURUSD", *split.validation)
                pobj = composite_objective(pm)
                perturbation_objs.append(pobj)
                _record(registry, strategy_id, "EURUSD", split, "perturbation", pw, [], pm, "Candidate",
                        notes=f"moved {fraction:.0%} of weight from {donor} to {receiver}")
    min_perturbed = min(perturbation_objs) if perturbation_objs else chosen_val_obj
    mean_perturbed = sum(perturbation_objs) / len(perturbation_objs) if perturbation_objs else chosen_val_obj
    print(f"perturbation validation-objective range: min={min_perturbed:.3f} mean={mean_perturbed:.3f} (unperturbed={chosen_val_obj:.3f})", flush=True)

    # --- Ablation (structural gates, on TRAIN, candidate weights held fixed) ---
    print("=== ablation (structural gates, on TRAIN) ===", flush=True)
    ablation_results = {}
    for gate_name, gate_const in gates.items():
        am = evaluate(strategy_cls(weights=chosen_weights, disabled_components=frozenset({gate_const})), "EURUSD", *split.train)
        aobj = composite_objective(am)
        _record(registry, strategy_id, "EURUSD", split, "ablation", chosen_weights, [gate_const], am, "Candidate",
                notes=f"ablated_gate={gate_name}")
        ablation_results[gate_name] = {"metrics": asdict(am), "objective": aobj}
        print(f"  ablate {gate_name}: resolved={am.resolved_count} net_r={am.net_r:.2f} obj={aobj:.3f} "
              f"(full-strategy train obj={chosen_train_obj:.3f})", flush=True)

    # --- XAUUSD generalization check (same weights, no re-search) ---
    print("=== XAUUSD generalization check (same weights, no re-search) ===", flush=True)
    xau_split = chronological_split(*full_window_for("XAUUSD"))
    xau_metrics = {}
    for phase, (start, end) in (("train", xau_split.train), ("validation", xau_split.validation), ("out_of_sample", xau_split.out_of_sample)):
        m = evaluate(strategy_cls(weights=chosen_weights), "XAUUSD", start, end)
        xau_metrics[phase] = {"metrics": asdict(m), "objective": composite_objective(m)}
        _record(registry, strategy_id, "XAUUSD", xau_split, phase, chosen_weights, [], m, "Candidate",
                notes="cross-symbol generalization check using EURUSD-derived weights, no re-search")
        print(f"[XAUUSD/{phase}] resolved={m.resolved_count} net_r={m.net_r:.2f} obj={composite_objective(m):.3f}", flush=True)

    elapsed = time.time() - t0
    print(f"=== {strategy_id} done in {elapsed:.1f}s ===", flush=True)

    summary = {
        "strategy": strategy_id, "min_confidence": MIN_CONFIDENCE,
        "default_weights": dict(default_weights.weights),
        "candidate_weights": dict(chosen_weights.weights),
        "baseline": {p: {"metrics": asdict(m), "objective": composite_objective(m)} for p, m in baseline_metrics.items()},
        "candidate_train_objective": chosen_train_obj,
        "candidate_validation": {"metrics": asdict(chosen_val_metrics), "objective": chosen_val_obj},
        "candidate_oos": {"metrics": asdict(oos_metrics), "objective": oos_obj},
        "perturbation": {"min_objective": min_perturbed, "mean_objective": mean_perturbed, "n_runs": len(perturbation_objs),
                          "unperturbed_validation_objective": chosen_val_obj},
        "ablation": ablation_results,
        "xauusd_generalization": xau_metrics,
        "all_train_search_results": [
            {"weights": dict(r.weights.weights), "objective": r.objective, "resolved_count": r.metrics.resolved_count}
            for r in search_results
        ],
        "elapsed_seconds": elapsed,
    }
    out_path = Path("data/optimization_results") / f"{strategy_key}_summary.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2, default=str))
    print(f"summary written to {out_path}", flush=True)
    return summary


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in STRATEGY_SPECS:
        print(f"usage: python {sys.argv[0]} <{'|'.join(STRATEGY_SPECS)}>")
        sys.exit(1)
    run(sys.argv[1])
