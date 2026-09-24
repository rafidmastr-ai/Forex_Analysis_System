"""Robustness (R:R-cap) backtest: for the same 96 Strategy x Symbol x
Timeframe configurations as the current-version Baseline
(data/optimization_results/m1_full_backtest.json), tests whether the
Baseline's edge depends heavily on a small number of extreme-R:R trades.

Runs each of the 96 configurations' signals EXACTLY ONCE (identical
production wiring to scripts/m1_full_backtest.py -- same strategies,
filters, min_confidence=None, min_risk_reward=1.5, timeframe mapping,
lookback, dataset, same-candle policy), then derives all 6 robustness
modes (Baseline + 5 R:R caps, see config/robustness_backtest.yaml) from
that SAME already-decided trade list via optimization.robustness
.apply_rr_cap -- a pure post-processing step on each trade's REALIZED R
(TradeOutcome.r_multiple), never a re-run of signal generation. This is
mathematically equivalent to re-running the backtest per cap (the cap
cannot affect which trades are taken, only their realized R), and is the
only reason 576 configurations are tractable from 96 actual backtests.

No Strategy/Weight/Filter/Threshold/Entry/TP/SL/Confidence/Timeframe-
mapping/Lookback/Dataset/same-candle-policy logic is touched anywhere in
this script.

Before trusting any capped number, this script validates that ITS OWN
freshly-computed Baseline (rr_cap=None) reproduces
data/optimization_results/m1_full_backtest.json's numbers for that exact
cell -- any mismatch is recorded, never silently absorbed.
"""
from __future__ import annotations

import json
import sys
import time
import traceback
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.market_data.models import Timeframe  # noqa: E402
from optimization.extended_metrics import compute_extended_metrics  # noqa: E402
from optimization.robustness import RobustnessMode, apply_rr_cap, load_robustness_modes  # noqa: E402
from optimization.runner import run_backtest  # noqa: E402
from scripts.data_window import full_window_for  # noqa: E402
from scripts.final_evaluation import (  # noqa: E402
    ADOPTED_STRATEGY_BUILDERS,
    _build_strategies,
    _production_selection_engine,
)
from scripts.m1_full_backtest import ENTRY_TIMEFRAMES, SAME_CANDLE_POLICY, SYMBOL_NAMES, _provider  # noqa: E402
from scripts.optimize_strategy import LOOKBACK_BARS, TIMEFRAMES_CONFIG  # noqa: E402

PREVIOUS_FULL_BACKTEST_PATH = Path("data/optimization_results/m1_full_backtest.json")
OUT_JSON = Path("data/optimization_results/robustness_backtest.json")
FLOAT_TOLERANCE = 1e-6


def _cell_metrics(outcomes) -> dict:
    m = compute_extended_metrics(outcomes)
    resolved = [o for o in outcomes if o.hit != "NONE"]
    d = asdict(m)
    d["tp1_count"] = sum(1 for o in resolved if o.hit == "TP1")
    d["tp2_count"] = sum(1 for o in resolved if o.hit == "TP2")
    d["sl_count"] = sum(1 for o in resolved if o.hit == "SL")
    return d


def run_one_signal_generation(strategy_name: str, symbol_name: str, tf_name: str):
    """Runs the strategy ONCE, exactly like scripts/m1_full_backtest.py's
    run_one -- identical production wiring, identical window -- and returns
    the raw TradeOutcome list (report.outcomes) for post-processing by
    every robustness mode."""
    provider = _provider()
    selection_engine = _production_selection_engine()
    strategies = _build_strategies([strategy_name])
    timeframe = Timeframe(tf_name)
    window = full_window_for(symbol_name)
    report = run_backtest(
        strategies=strategies, provider=provider, selection_engine=selection_engine,
        symbol_name=symbol_name, timeframe=timeframe, start=window[0], end=window[1],
        timeframes_config=TIMEFRAMES_CONFIG, lookback_bars=LOOKBACK_BARS, min_confidence=None,
    )
    return report.outcomes


def _numeric_close(a, b, tol: float = FLOAT_TOLERANCE) -> bool:
    if a == b:
        return True
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if a == float("inf") or b == float("inf"):
            return a == b
        return abs(a - b) <= tol
    return False


def validate_baseline_against_previous(strategy_name: str, symbol_name: str, tf_name: str,
                                        baseline_outcomes, previous_full_backtest: dict | None) -> list[str]:
    """Compares this run's freshly-computed Baseline cell against the
    already-delivered m1_full_backtest.json's SAME cell. Returns mismatch
    descriptions (empty list = exact match, within floating tolerance)."""
    if previous_full_backtest is None:
        return [f"{PREVIOUS_FULL_BACKTEST_PATH} not found -- cannot validate baseline reproducibility"]
    prev_cell = previous_full_backtest.get("results", {}).get(strategy_name, {}).get(symbol_name, {}).get(tf_name)
    if prev_cell is None or prev_cell.get("status") == "FAILED":
        return [f"no comparable prior cell for {strategy_name}/{symbol_name}/{tf_name}"]

    fresh = _cell_metrics(baseline_outcomes)
    checks = [
        ("trade_count", prev_cell["trade_count"], fresh["trade_count"]),
        ("resolved_count", prev_cell["resolved_count"], fresh["resolved_count"]),
        ("none_count", prev_cell["none_count"], fresh["none_count"]),
        ("tp1_count", prev_cell["tp1_count"], fresh["tp1_count"]),
        ("tp2_count", prev_cell["tp2_count"], fresh["tp2_count"]),
        ("sl_count", prev_cell["sl_count"], fresh["sl_count"]),
        ("win_rate", prev_cell["metrics"]["win_rate"], fresh["win_rate"]),
        ("net_r", prev_cell["metrics"]["net_r"], fresh["net_r"]),
        ("profit_factor", prev_cell["metrics"]["profit_factor"], fresh["profit_factor"]),
        ("expectancy", prev_cell["metrics"]["expectancy"], fresh["expectancy"]),
        ("max_drawdown_r", prev_cell["metrics"]["max_drawdown_r"], fresh["max_drawdown_r"]),
    ]
    return [f"{name}: previous={expected}, fresh={actual}" for name, expected, actual in checks
            if not _numeric_close(expected, actual)]


def run_cell(strategy_name: str, symbol_name: str, tf_name: str, modes: list[RobustnessMode],
             previous_full_backtest: dict | None) -> dict:
    t0 = time.time()
    outcomes = run_one_signal_generation(strategy_name, symbol_name, tf_name)

    by_mode = {}
    baseline_outcomes = None
    for mode in modes:
        capped = apply_rr_cap(outcomes, mode.rr_cap)
        if mode.rr_cap is None:
            baseline_outcomes = capped
        by_mode[mode.label] = _cell_metrics(capped)

    mismatches = validate_baseline_against_previous(strategy_name, symbol_name, tf_name,
                                                      baseline_outcomes if baseline_outcomes is not None else outcomes,
                                                      previous_full_backtest)

    elapsed = time.time() - t0
    print(f"[{strategy_name}/{symbol_name}/{tf_name}] trades={len(outcomes)} "
          f"baseline_net_r={by_mode['Baseline']['net_r']:.2f} "
          f"cap2_net_r={by_mode.get('Cap_2.0', {}).get('net_r', float('nan')):.2f} "
          f"{'MISMATCH!' if mismatches else 'validated'} ({elapsed:.1f}s)", flush=True)

    return {"by_mode": by_mode, "baseline_validation_mismatches": mismatches, "elapsed_seconds": elapsed}


def run_smoke_validation(modes: list[RobustnessMode], previous_full_backtest: dict | None,
                          sample: list[tuple[str, str, str]]) -> bool:
    """Cheap, small-sample gate BEFORE committing to the full 96-cell run
    (per the explicit instruction: only run the full 576-configuration
    matrix if this passes). Returns True iff every sampled cell's Baseline
    matches the previous full backtest exactly."""
    print("=== smoke validation (small sample, before the full run) ===", flush=True)
    all_ok = True
    for strategy_name, symbol_name, tf_name in sample:
        result = run_cell(strategy_name, symbol_name, tf_name, modes, previous_full_backtest)
        if result["baseline_validation_mismatches"]:
            all_ok = False
            print(f"  MISMATCH at {strategy_name}/{symbol_name}/{tf_name}: {result['baseline_validation_mismatches']}", flush=True)
    print(f"=== smoke validation {'PASSED' if all_ok else 'FAILED'} ===\n", flush=True)
    return all_ok


def main() -> None:
    modes = load_robustness_modes()
    previous_full_backtest = json.loads(PREVIOUS_FULL_BACKTEST_PATH.read_text()) if PREVIOUS_FULL_BACKTEST_PATH.exists() else None

    smoke_sample = [("ICT", "EURUSD", "H4"), ("Classic", "GBPUSD", "H1"), ("SweepDisplacement", "NZDUSD", "M30")]
    if not run_smoke_validation(modes, previous_full_backtest, smoke_sample):
        print("FULL BACKTEST INCOMPLETE -- smoke validation failed, refusing to run the full 576-configuration matrix.", flush=True)
        raise SystemExit(1)

    all_results: dict = {
        "dataset_source": "data/market/{SYMBOL}.csv",
        "baseline_reference": str(PREVIOUS_FULL_BACKTEST_PATH),
        "same_candle_policy": SAME_CANDLE_POLICY,
        "timeframe_mapping": TIMEFRAMES_CONFIG.get("entry_mapping"),
        "lookback_configuration": LOOKBACK_BARS,
        "modes": [{"label": m.label, "rr_cap": m.rr_cap} for m in modes],
        "strategies": list(ADOPTED_STRATEGY_BUILDERS), "symbols": SYMBOL_NAMES,
        "timeframes": ENTRY_TIMEFRAMES, "results": {},
    }

    errors: list[dict] = []
    all_mismatches: dict[str, list[str]] = {}
    successful = 0
    failed = 0
    total_runs = len(ADOPTED_STRATEGY_BUILDERS) * len(SYMBOL_NAMES) * len(ENTRY_TIMEFRAMES)

    t_start = time.time()
    for strategy_name in ADOPTED_STRATEGY_BUILDERS:
        all_results["results"][strategy_name] = {}
        for symbol_name in SYMBOL_NAMES:
            all_results["results"][strategy_name][symbol_name] = {}
            for tf_name in ENTRY_TIMEFRAMES:
                try:
                    cell = run_cell(strategy_name, symbol_name, tf_name, modes, previous_full_backtest)
                    all_results["results"][strategy_name][symbol_name][tf_name] = cell
                    if cell["baseline_validation_mismatches"]:
                        all_mismatches[f"{strategy_name}/{symbol_name}/{tf_name}"] = cell["baseline_validation_mismatches"]
                    successful += 1
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    error_record = {
                        "strategy": strategy_name, "symbol": symbol_name, "timeframe": tf_name,
                        "error_type": type(exc).__name__, "error_message": str(exc),
                        "traceback": traceback.format_exc(),
                    }
                    errors.append(error_record)
                    all_results["results"][strategy_name][symbol_name][tf_name] = {"status": "FAILED", **error_record}
                    print(f"[{strategy_name}/{symbol_name}/{tf_name}] FAILED: {type(exc).__name__}: {exc}", flush=True)

                all_results["run_status"] = {
                    "total_runs": total_runs, "successful_runs": successful, "failed_runs": failed,
                    "errors": errors, "baseline_validation_mismatches": all_mismatches,
                    "elapsed_seconds_so_far": time.time() - t_start,
                }
                OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
                OUT_JSON.write_text(json.dumps(all_results, indent=2, default=str))

    total_elapsed = time.time() - t_start
    all_results["run_status"]["total_elapsed_seconds"] = total_elapsed
    OUT_JSON.write_text(json.dumps(all_results, indent=2, default=str))

    print(f"\n=== RUN SUMMARY: {successful}/{total_runs} succeeded, {failed}/{total_runs} failed, "
          f"{len(all_mismatches)} baseline mismatches, in {total_elapsed / 60:.1f} minutes ===", flush=True)
    if failed or all_mismatches:
        print("\nFULL BACKTEST INCOMPLETE", flush=True)
    else:
        print("\nFULL BACKTEST COMPLETE", flush=True)
    print(f"summary written to {OUT_JSON}", flush=True)


if __name__ == "__main__":
    main()
