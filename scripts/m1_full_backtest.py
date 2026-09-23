"""Full current-version backtest across every adopted strategy, all four
supported symbols (EURUSD, XAUUSD, GBPUSD, NZDUSD), and all six requested
entry timeframes (M1/M5/M15/M30/H1/H4), using ONLY the raw M1 OHLC data
checked into data/market/ (and the M5/M15/M30/H1/H4 files built from it by
scripts/build_m1_historical_data.py). No previously existing/deleted
EURUSD/XAUUSD dataset, and no temporary upload path, is read anywhere in
this script.

This is an evaluation-only pass: NOT an optimization step. No Strategy,
Weight, Threshold, Entry, TP, SL, or Filter logic is changed here. Each
strategy is tested INDEPENDENTLY (no combinations) through the exact
current production `StrategySelectionEngine` wiring (imported from
scripts.final_evaluation, itself a verbatim mirror of backend/dependencies
.py) -- same convention as the current-version evaluation phase: filters =
[VolatilityRegimeFilter(), HTFTrendAlignmentFilter()], min_confidence=None
(confidence never gates trades in production /analyze), min_risk_reward is
whatever StrategySelectionEngine/_production_selection_engine already use
(1.5, unchanged) -- a rejected (REJECTED_MIN_RR) setup never becomes a
TradeOutcome (see backtesting/engine.py's `if setup.status != SELECTED:
continue`), so it is never counted as an executed trade below.

Higher/Middle timeframe roles now come from config/settings.backtest.yaml's
`timeframes.entry_mapping` table (see that file's comments and
core/context/timeframe_selector.py's resolve_for_entry -- BacktestEngine
picks this up automatically once TIMEFRAMES_CONFIG, loaded from that same
YAML by scripts/optimize_strategy.py, contains 'entry_mapping'), rather
than the single static H4/H1 pair used for every entry timeframe by an
earlier version of this script. LOOKBACK_BARS is unchanged from the
existing production default (higher=200, middle=300, entry=500 bars) for
every entry timeframe -- the wall-clock span covered by 500 bars obviously
differs hugely between M1 (500 bars) and H4 (500 bars, ~83 days); this is
recorded, not hidden, in the output summary's "lookback_configuration".

Each symbol's actual (start, end) window is read from
scripts.data_window.full_window_for(), itself derived from
scripts/build_m1_historical_data.py's own detection of the uploaded CSVs --
never a hard-coded date range, and never assumed identical across symbols
(this dataset's four symbols do NOT all share the same end date -- see the
per-symbol "actual_start"/"actual_end" recorded in every result below).

Regime buckets (low/medium/high) are computed the same way
VolatilityRegimeFilter itself computes them in production: ATR(14) on the
run's own entry-timeframe candles, classified point-in-time (only candles
up to and including the signal's own bar).

Same-candle TP/SL policy (recorded in the output for traceability, not
changed here): backtesting/engine.py's `_simulate_outcome` checks SL before
TP1/TP2 on any candle where both would be touched -- a deterministic,
conservative convention, documented because M1 OHLC (like every other
timeframe here) cannot establish true intrabar ordering.
"""
from __future__ import annotations

import bisect
import json
import sys
import time
import traceback
from dataclasses import asdict
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.historical_file.file_adapter import HistoricalFileMarketDataProvider  # noqa: E402
from core.algorithms.indicators.atr import atr  # noqa: E402
from core.algorithms.volatility.volatility import classify_volatility  # noqa: E402
from core.market_data.models import Timeframe  # noqa: E402
from optimization.extended_metrics import compute_extended_metrics  # noqa: E402
from optimization.runner import run_backtest  # noqa: E402
from scripts.data_window import BUILD_REPORT_PATH, full_window_for  # noqa: E402
from scripts.final_evaluation import (  # noqa: E402
    ADOPTED_STRATEGY_BUILDERS,
    _build_strategies,
    _load_session_defs,
    _production_selection_engine,
    _session_for,
)
from scripts.optimize_strategy import LOOKBACK_BARS, SYMBOLS, TIMEFRAMES_CONFIG  # noqa: E402

SYMBOL_NAMES = ["EURUSD", "XAUUSD", "GBPUSD", "NZDUSD"]
ENTRY_TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4"]

SAME_CANDLE_POLICY = (
    "SL checked before TP1/TP2 whenever both would be touched within the same "
    "OHLC candle (backtesting/engine.py:_simulate_outcome) -- a deterministic, "
    "conservative convention; intrabar order cannot be established from OHLC data."
)

DURATION_BUCKETS = [
    ("<15min", 0, 15), ("15-30min", 15, 30), ("30-60min", 30, 60),
    ("1-2h", 60, 120), ("2-4h", 120, 240), (">4h", 240, float("inf")),
]


def _provider() -> HistoricalFileMarketDataProvider:
    return HistoricalFileMarketDataProvider(data_dir=Path("data/historical"), symbols=SYMBOLS)


def _duration_bucket(minutes: float) -> str:
    for label, lo, hi in DURATION_BUCKETS:
        if lo <= minutes < hi:
            return label
    return ">4h"


def _metrics_dict(outcomes) -> dict:
    return asdict(compute_extended_metrics(outcomes))


def _duration_breakdown(resolved_outcomes) -> dict:
    buckets: dict[str, list] = {label: [] for label, _, _ in DURATION_BUCKETS}
    for o in resolved_outcomes:
        if o.closed_at is None:
            continue
        minutes = (o.closed_at - o.opened_at).total_seconds() / 60
        buckets[_duration_bucket(minutes)].append(o)
    return {label: _metrics_dict(v) for label, v in buckets.items() if v}


def _direction_breakdown(outcomes) -> dict:
    out = {}
    for direction_name in ("BUY", "SELL"):
        subset = [o for o in outcomes if o.setup.direction.value == direction_name]
        if subset:
            out[direction_name] = _metrics_dict(subset)
    return out


def _regime_session_breakdown(outcomes, provider, symbol_name: str, timeframe: Timeframe, session_defs) -> tuple[dict, dict]:
    resolved = [o for o in outcomes if o.hit != "NONE"]
    if not resolved:
        return {}, {}
    symbol = provider.get_symbol_info(symbol_name)
    entry_series = provider.get_ohlcv(symbol, timeframe, count=1_000_000)
    timestamps = [c.timestamp for c in entry_series.candles]
    atr_values = atr(entry_series.candles, period=14)

    regime_buckets: dict[str, list] = {}
    session_buckets: dict[str, list] = {}
    for outcome in resolved:
        idx = max(0, bisect.bisect_right(timestamps, outcome.opened_at) - 1)
        regime = classify_volatility(atr_values[: idx + 1])
        session = _session_for(outcome.opened_at, session_defs)
        regime_buckets.setdefault(regime, []).append(outcome)
        session_buckets.setdefault(session, []).append(outcome)

    by_regime = {k: _metrics_dict(v) for k, v in regime_buckets.items()}
    by_session = {k: _metrics_dict(v) for k, v in session_buckets.items()}
    return by_regime, by_session


def run_one(strategy_name: str, symbol_name: str, tf_name: str, session_defs) -> dict:
    t0 = time.time()
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
    resolved = report.resolved_outcomes
    m = compute_extended_metrics(report.outcomes)

    durations = [(o.closed_at - o.opened_at).total_seconds() / 60 for o in resolved if o.closed_at is not None]

    by_regime, by_session = _regime_session_breakdown(report.outcomes, provider, symbol_name, timeframe, session_defs)

    result = {
        "dataset_source": f"data/market/{symbol_name}.csv", "strategy": strategy_name,
        "symbol": symbol_name, "timeframe": tf_name,
        "actual_start": window[0].isoformat(), "actual_end": window[1].isoformat(),
        "trade_count": m.trade_count, "resolved_count": m.resolved_count, "none_count": m.none_count,
        "tp1_count": sum(1 for o in resolved if o.hit == "TP1"),
        "tp2_count": sum(1 for o in resolved if o.hit == "TP2"),
        "sl_count": sum(1 for o in resolved if o.hit == "SL"),
        "metrics": asdict(m),
        "median_duration_minutes": median(durations) if durations else None,
        "duration_breakdown": _duration_breakdown(resolved),
        "direction_breakdown": _direction_breakdown(report.outcomes),
        "regime_breakdown": by_regime,
        "session_breakdown": by_session,
        "elapsed_seconds": time.time() - t0,
    }
    print(f"[{strategy_name}/{symbol_name}/{tf_name}] trades={m.trade_count} resolved={m.resolved_count} "
          f"win_rate={m.win_rate:.3f} net_r={m.net_r:.2f} pf={m.profit_factor:.2f} "
          f"({result['elapsed_seconds']:.1f}s)", flush=True)
    return result


def main() -> None:
    session_defs = _load_session_defs()

    if not BUILD_REPORT_PATH.exists():
        raise FileNotFoundError(
            f"{BUILD_REPORT_PATH} not found -- run `python scripts/build_m1_historical_data.py` first."
        )
    build_report = json.loads(BUILD_REPORT_PATH.read_text())

    per_symbol_data = {}
    for symbol_name in SYMBOL_NAMES:
        if symbol_name not in build_report:
            raise KeyError(f"{symbol_name} missing from {BUILD_REPORT_PATH} -- was it included in the last build?")
        info = build_report[symbol_name]
        per_symbol_data[symbol_name] = {
            "source_m1_candles": info["m1_rows"],
            "actual_start": info["start_utc"], "actual_end": info["end_utc"],
            "generated_candle_counts": {tf: v["n_buckets"] for tf, v in info["timeframes"].items()},
            "incomplete_trailing_buckets_removed": {
                tf: v.get("cross_validation_issues", []) for tf, v in info["timeframes"].items()
            },
            "cross_validation_passed_all_timeframes": all(v["cross_validation_passed"] for v in info["timeframes"].values()),
        }
    data_validation_status = "PASSED" if all(d["cross_validation_passed_all_timeframes"] for d in per_symbol_data.values()) else "FAILED"

    all_results: dict = {
        "dataset_source": "data/market/{SYMBOL}.csv (see M1_DATA_QUALITY_REPORT.md)",
        "data_validation_status": data_validation_status,
        "per_symbol_data": per_symbol_data,
        "same_candle_policy": SAME_CANDLE_POLICY,
        "timeframe_mapping": TIMEFRAMES_CONFIG.get("entry_mapping"),
        "lookback_configuration": LOOKBACK_BARS,
        "strategies": list(ADOPTED_STRATEGY_BUILDERS), "symbols": SYMBOL_NAMES,
        "timeframes": ENTRY_TIMEFRAMES, "results": {},
    }

    errors: list[dict] = []
    successful = 0
    failed = 0
    total_runs = len(ADOPTED_STRATEGY_BUILDERS) * len(SYMBOL_NAMES) * len(ENTRY_TIMEFRAMES)

    t_start = time.time()
    for strategy_name in ADOPTED_STRATEGY_BUILDERS:
        all_results["results"][strategy_name] = {}
        for symbol_name in SYMBOL_NAMES:
            all_results["results"][strategy_name][symbol_name] = {}
            for tf_name in ENTRY_TIMEFRAMES:
                # A single combination's runtime failure must not lose the
                # other 95 independent runs, and must never be silently
                # dropped either -- recorded verbatim in both the JSON and
                # the run log, never patched over by changing any strategy/
                # weight/filter/threshold logic.
                try:
                    result = run_one(strategy_name, symbol_name, tf_name, session_defs)
                    all_results["results"][strategy_name][symbol_name][tf_name] = result
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

                out_path = Path("data/optimization_results/m1_full_backtest.json")
                out_path.parent.mkdir(parents=True, exist_ok=True)
                all_results["run_status"] = {
                    "total_runs": total_runs, "successful_runs": successful, "failed_runs": failed,
                    "errors": errors, "elapsed_seconds_so_far": time.time() - t_start,
                }
                out_path.write_text(json.dumps(all_results, indent=2, default=str))

    total_elapsed = time.time() - t_start
    all_results["run_status"]["total_elapsed_seconds"] = total_elapsed
    out_path = Path("data/optimization_results/m1_full_backtest.json")
    out_path.write_text(json.dumps(all_results, indent=2, default=str))

    print(f"\n=== RUN SUMMARY: {successful}/{total_runs} succeeded, {failed}/{total_runs} failed "
          f"in {total_elapsed / 60:.1f} minutes ===", flush=True)
    if failed:
        for e in errors:
            print(f"  FAILED: {e['strategy']}/{e['symbol']}/{e['timeframe']} -- {e['error_type']}: {e['error_message']}", flush=True)
        print("\nFULL BACKTEST INCOMPLETE", flush=True)
    else:
        print("\nFULL BACKTEST COMPLETE", flush=True)
    print("summary written to data/optimization_results/m1_full_backtest.json", flush=True)


if __name__ == "__main__":
    main()
