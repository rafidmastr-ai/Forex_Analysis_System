"""R:R Distribution Audit: determines whether the current-version Baseline
backtest's performance (data/optimization_results/m1_full_backtest.json)
depends on a small number of trades with extremely large realized R
multiples.

Runs the SAME 96 Strategy x Symbol x Entry-Timeframe configurations as the
Baseline -- via scripts.robustness_backtest.run_one_signal_generation,
identical production wiring, reused verbatim -- captures every already-
decided TradeOutcome's fields, and only THEN runs purely descriptive,
analytical post-processing (optimization.rr_distribution) over that fixed
trade list. No Strategy/Weight/Filter/Threshold/Entry/TP/SL/Confidence/
Timeframe-mapping/Lookback/Dataset/same-candle-policy/position-sizing/
trade-selection logic is touched, read differently, or re-run more than
once anywhere in this script. This is a diagnostic audit only: it does not
rank strategies/symbols/timeframes and recommends nothing.

Before trusting any distribution statistic, this script validates that its
own freshly-computed Baseline reproduces
data/optimization_results/m1_full_backtest.json's numbers EXACTLY for every
one of the 96 cells (trade_count, resolved_count, wins, losses, TP1, TP2,
SL, win_rate, net_r, profit_factor, expectancy) -- any mismatch is recorded
and reported, never silently absorbed.
"""
from __future__ import annotations

import bisect
import json
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.algorithms.indicators.atr import atr  # noqa: E402
from core.algorithms.volatility.volatility import classify_volatility  # noqa: E402
from optimization.extended_metrics import compute_extended_metrics  # noqa: E402
from optimization.rr_distribution import independent_r_multiple  # noqa: E402
from scripts.final_evaluation import ADOPTED_STRATEGY_BUILDERS, _load_session_defs, _session_for  # noqa: E402
from scripts.m1_full_backtest import ENTRY_TIMEFRAMES, SYMBOL_NAMES, _provider  # noqa: E402
from scripts.robustness_backtest import run_one_signal_generation  # noqa: E402

PREVIOUS_FULL_BACKTEST_PATH = Path("data/optimization_results/m1_full_backtest.json")
OUT_JSON = Path("data/optimization_results/trade_level_audit.json")
FLOAT_TOLERANCE = 1e-6
R_VALIDATION_TOLERANCE = 1e-6


def _numeric_close(a, b, tol: float = FLOAT_TOLERANCE) -> bool:
    if a == b:
        return True
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if a == float("inf") or b == float("inf"):
            return a == b
        return abs(a - b) <= tol
    return False


def _cell_metrics(outcomes) -> dict:
    m = compute_extended_metrics(outcomes)
    resolved = [o for o in outcomes if o.hit != "NONE"]
    return {
        "trade_count": m.trade_count, "resolved_count": m.resolved_count, "none_count": m.none_count,
        "tp1_count": sum(1 for o in resolved if o.hit == "TP1"),
        "tp2_count": sum(1 for o in resolved if o.hit == "TP2"),
        "sl_count": sum(1 for o in resolved if o.hit == "SL"),
        "win_rate": m.win_rate, "net_r": m.net_r, "profit_factor": m.profit_factor,
        "expectancy": m.expectancy,
    }


def validate_baseline_against_previous(strategy_name: str, symbol_name: str, tf_name: str,
                                        outcomes, previous_full_backtest: dict | None) -> list[str]:
    """Item 13's Baseline Integrity Check for one cell -- compares this
    audit's freshly-computed cell against the already-delivered
    m1_full_backtest.json's SAME cell. Empty list = exact match (within
    floating tolerance)."""
    if previous_full_backtest is None:
        return [f"{PREVIOUS_FULL_BACKTEST_PATH} not found -- cannot validate baseline reproducibility"]
    prev_cell = previous_full_backtest.get("results", {}).get(strategy_name, {}).get(symbol_name, {}).get(tf_name)
    if prev_cell is None or prev_cell.get("status") == "FAILED":
        return [f"no comparable prior cell for {strategy_name}/{symbol_name}/{tf_name}"]

    fresh = _cell_metrics(outcomes)
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
    ]
    return [f"{name}: previous={expected}, fresh={actual}" for name, expected, actual in checks
            if not _numeric_close(expected, actual)]


def _exit_price(setup, hit: str) -> float | None:
    """The exact exit price BacktestEngine._simulate_outcome used to decide
    `hit`/`r_multiple` -- read directly, never re-derived or guessed."""
    if hit == "TP1":
        return setup.take_profit_1
    if hit == "TP2":
        return setup.take_profit_2
    if hit == "SL":
        return setup.stop_loss
    return None


def _regime_and_session_lookup(provider, symbol_name: str, timeframe, session_defs):
    """Point-in-time regime classification, identical method to
    scripts/m1_full_backtest.py's _regime_session_breakdown (ATR(14) on the
    run's own entry-timeframe candles, bisected up to and including the
    signal's own bar) -- reused, not reimplemented differently."""
    symbol = provider.get_symbol_info(symbol_name)
    entry_series = provider.get_ohlcv(symbol, timeframe, count=1_000_000)
    timestamps = [c.timestamp for c in entry_series.candles]
    atr_values = atr(entry_series.candles, period=14)

    def lookup(opened_at):
        idx = max(0, bisect.bisect_right(timestamps, opened_at) - 1)
        regime = classify_volatility(atr_values[: idx + 1])
        session = _session_for(opened_at, session_defs)
        return regime, session

    return lookup


def build_trade_records(strategy_name: str, symbol_name: str, tf_name: str, outcomes, regime_session_lookup) -> list[dict]:
    """Item 3's full trade-level record set, captured AFTER TradeOutcome is
    already produced -- nothing here influences which trades were taken or
    how they were resolved."""
    records = []
    for o in outcomes:
        setup = o.setup
        exit_price = _exit_price(setup, o.hit)
        independent_r = None
        r_discrepancy = None
        if exit_price is not None:
            independent_r = independent_r_multiple(
                setup.direction.value, entry=setup.entry, stop_loss=setup.stop_loss, exit_price=exit_price,
            )
            if independent_r is not None:
                r_discrepancy = independent_r - o.r_multiple
        regime, session = regime_session_lookup(o.opened_at)
        duration_minutes = (o.closed_at - o.opened_at).total_seconds() / 60 if o.closed_at is not None else None

        winning_signal = setup.winning_signal
        records.append({
            "strategy": strategy_name, "symbol": symbol_name, "timeframe": tf_name,
            "opened_at": o.opened_at.isoformat(), "closed_at": o.closed_at.isoformat() if o.closed_at else None,
            "direction": setup.direction.value,
            "entry": setup.entry, "stop_loss": setup.stop_loss,
            "take_profit_1": setup.take_profit_1, "take_profit_2": setup.take_profit_2,
            "hit": o.hit, "r_multiple": o.r_multiple,
            "planned_rr_tp1": setup.risk_reward_tp1, "planned_rr_tp2": setup.risk_reward_tp2,
            "duration_minutes": duration_minutes,
            "confidence_score": setup.confidence_score, "confidence_label": setup.confidence_label,
            "session": session, "volatility_regime": regime,
            "selected_strategy_display": setup.selected_strategy_display,
            "signal_score_raw_components": dict(winning_signal.raw_score_components) if winning_signal is not None else None,
            "independent_r_multiple": independent_r,
            "r_multiple_discrepancy": r_discrepancy,
        })
    return records


def run_cell(strategy_name: str, symbol_name: str, tf_name: str, previous_full_backtest: dict | None,
             session_defs) -> tuple[dict, list[dict]]:
    t0 = time.time()
    outcomes = run_one_signal_generation(strategy_name, symbol_name, tf_name)
    mismatches = validate_baseline_against_previous(strategy_name, symbol_name, tf_name, outcomes, previous_full_backtest)

    provider = _provider()
    from core.market_data.models import Timeframe
    timeframe = Timeframe(tf_name)
    regime_session_lookup = _regime_and_session_lookup(provider, symbol_name, timeframe, session_defs)
    records = build_trade_records(strategy_name, symbol_name, tf_name, outcomes, regime_session_lookup)

    elapsed = time.time() - t0
    cell_summary = {"metrics": _cell_metrics(outcomes), "baseline_validation_mismatches": mismatches,
                     "elapsed_seconds": elapsed}
    print(f"[{strategy_name}/{symbol_name}/{tf_name}] trades={len(outcomes)} "
          f"{'MISMATCH!' if mismatches else 'validated'} ({elapsed:.1f}s)", flush=True)
    return cell_summary, records


def main() -> None:
    previous_full_backtest = json.loads(PREVIOUS_FULL_BACKTEST_PATH.read_text()) if PREVIOUS_FULL_BACKTEST_PATH.exists() else None
    if previous_full_backtest is None:
        print(f"FULL AUDIT INCOMPLETE -- {PREVIOUS_FULL_BACKTEST_PATH} not found.", flush=True)
        raise SystemExit(1)
    session_defs = _load_session_defs()

    all_cells: dict = {}
    all_trades: list[dict] = []
    errors: list[dict] = []
    all_mismatches: dict[str, list[str]] = {}
    successful = 0
    failed = 0
    total_runs = len(ADOPTED_STRATEGY_BUILDERS) * len(SYMBOL_NAMES) * len(ENTRY_TIMEFRAMES)

    t_start = time.time()
    for strategy_name in ADOPTED_STRATEGY_BUILDERS:
        all_cells[strategy_name] = {}
        for symbol_name in SYMBOL_NAMES:
            all_cells[strategy_name][symbol_name] = {}
            for tf_name in ENTRY_TIMEFRAMES:
                try:
                    cell_summary, records = run_cell(strategy_name, symbol_name, tf_name, previous_full_backtest, session_defs)
                    all_cells[strategy_name][symbol_name][tf_name] = cell_summary
                    all_trades.extend(records)
                    if cell_summary["baseline_validation_mismatches"]:
                        all_mismatches[f"{strategy_name}/{symbol_name}/{tf_name}"] = cell_summary["baseline_validation_mismatches"]
                    successful += 1
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    error_record = {
                        "strategy": strategy_name, "symbol": symbol_name, "timeframe": tf_name,
                        "error_type": type(exc).__name__, "error_message": str(exc),
                        "traceback": traceback.format_exc(),
                    }
                    errors.append(error_record)
                    all_cells[strategy_name][symbol_name][tf_name] = {"status": "FAILED", **error_record}
                    print(f"[{strategy_name}/{symbol_name}/{tf_name}] FAILED: {type(exc).__name__}: {exc}", flush=True)

    total_elapsed = time.time() - t_start

    r_discrepancies = [t for t in all_trades if t["r_multiple_discrepancy"] is not None
                        and abs(t["r_multiple_discrepancy"]) > R_VALIDATION_TOLERANCE]

    output = {
        "baseline_reference": str(PREVIOUS_FULL_BACKTEST_PATH),
        "strategies": list(ADOPTED_STRATEGY_BUILDERS), "symbols": SYMBOL_NAMES, "timeframes": ENTRY_TIMEFRAMES,
        "run_status": {
            "total_runs": total_runs, "successful_runs": successful, "failed_runs": failed,
            "errors": errors, "baseline_validation_mismatches": all_mismatches,
            "total_elapsed_seconds": total_elapsed,
        },
        "r_multiple_validation": {
            "trades_checked": sum(1 for t in all_trades if t["independent_r_multiple"] is not None),
            "trades_with_undefined_sl_distance": sum(1 for t in all_trades if t["hit"] != "NONE" and t["independent_r_multiple"] is None),
            "discrepancies_found": len(r_discrepancies),
            "discrepancy_samples": r_discrepancies[:50],
        },
        "cells": all_cells,
        "trades": all_trades,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(output, indent=2, default=str))

    print(f"\n=== AUDIT RUN SUMMARY: {successful}/{total_runs} cells succeeded, {failed}/{total_runs} failed, "
          f"{len(all_mismatches)} baseline mismatches, {len(all_trades)} trades captured, "
          f"{len(r_discrepancies)} R-multiple discrepancies, in {total_elapsed / 60:.1f} minutes ===", flush=True)
    if failed or all_mismatches or r_discrepancies:
        print("\nAUDIT DATA COLLECTION INCOMPLETE OR DISCREPANT -- see run_status/r_multiple_validation above.", flush=True)
    else:
        print("\nAUDIT DATA COLLECTION COMPLETE", flush=True)
    print(f"trade-level data written to {OUT_JSON}", flush=True)


if __name__ == "__main__":
    main()
