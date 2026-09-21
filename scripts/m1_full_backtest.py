"""Full current-version backtest across every adopted strategy, both
symbols, and all six requested entry timeframes (M1/M5/M15/M30/H1/H4),
using ONLY the newly-uploaded M1 OHLC data (and the M5/M15/M30/H1/H4 files
built from it by scripts/build_m1_historical_data.py). No previously
existing EURUSD/XAUUSD data is read anywhere in this script.

This is an evaluation-only pass: NOT an optimization step. No Strategy,
Weight, Threshold, Entry, TP, SL, or Filter logic is changed here. Each
strategy is tested INDEPENDENTLY (no combinations) through the exact
current production `StrategySelectionEngine` wiring (imported from
scripts.final_evaluation, itself a verbatim mirror of backend/dependencies
.py) -- same convention as the current-version evaluation phase: filters =
[VolatilityRegimeFilter(), HTFTrendAlignmentFilter()], min_confidence=None
(confidence never gates trades in production /analyze).

Higher/Middle timeframe roles (TimeframesConfig.default_mapping) are held
FIXED at H4/H1 -- the existing production default -- for every entry
timeframe tested, exactly as the current architecture defines them
(default_mapping is a static config value, never derived from the entry
timeframe by any existing code). This is not a new invented mapping: it is
the current version's config used as-is. A consequence, documented here
rather than hidden, is that for entry=H1 the "middle" role is the SAME
timeframe as entry, and for entry=H4 both "middle" (H1) and "higher" (H4)
are at or below the entry timeframe's own resolution -- the current
architecture has no rule that derives Higher/Middle from an arbitrary
entry timeframe, so this is simply what running the existing config
against a coarser entry timeframe produces. LOOKBACK_BARS is likewise held
at the existing production default (higher=200, middle=300, entry=500
bars) for every entry timeframe -- unchanged from the current version,
though the wall-clock span covered by 500 bars obviously differs hugely
between M1 (500 bars) and H4 (500 bars, ~83 days).

Regime buckets (low/medium/high) are computed the same way
VolatilityRegimeFilter itself computes them in production: ATR(14) on the
run's own entry-timeframe candles, classified point-in-time (only candles
up to and including the signal's own bar).
"""
from __future__ import annotations

import bisect
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.historical_file.file_adapter import HistoricalFileMarketDataProvider  # noqa: E402
from core.algorithms.indicators.atr import atr  # noqa: E402
from core.algorithms.volatility.volatility import classify_volatility  # noqa: E402
from core.market_data.models import Timeframe  # noqa: E402
from optimization.extended_metrics import compute_extended_metrics  # noqa: E402
from optimization.runner import run_backtest  # noqa: E402
from scripts.final_evaluation import (  # noqa: E402
    ADOPTED_STRATEGY_BUILDERS,
    _build_strategies,
    _load_session_defs,
    _production_selection_engine,
    _session_for,
)
from scripts.optimize_strategy import LOOKBACK_BARS, SYMBOLS, TIMEFRAMES_CONFIG  # noqa: E402

# The new M1 upload's actual, verified available range (see the Data
# Quality Report) -- identical for both symbols. NOT scripts.optimize_
# strategy.FULL_WINDOW, which describes the now-deleted, unrelated old
# dataset's date range.
FULL_WINDOW = (datetime(2025, 9, 1, tzinfo=timezone.utc), datetime(2026, 8, 31, 23, 59, tzinfo=timezone.utc))

SYMBOL_NAMES = ["EURUSD", "XAUUSD"]
ENTRY_TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4"]

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

    report = run_backtest(
        strategies=strategies, provider=provider, selection_engine=selection_engine,
        symbol_name=symbol_name, timeframe=timeframe, start=FULL_WINDOW[0], end=FULL_WINDOW[1],
        timeframes_config=TIMEFRAMES_CONFIG, lookback_bars=LOOKBACK_BARS, min_confidence=None,
    )
    resolved = report.resolved_outcomes
    m = compute_extended_metrics(report.outcomes)

    durations = [(o.closed_at - o.opened_at).total_seconds() / 60 for o in resolved if o.closed_at is not None]

    by_regime, by_session = _regime_session_breakdown(report.outcomes, provider, symbol_name, timeframe, session_defs)

    result = {
        "strategy": strategy_name, "symbol": symbol_name, "timeframe": tf_name,
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
    all_results: dict = {"window": [FULL_WINDOW[0].isoformat(), FULL_WINDOW[1].isoformat()],
                          "strategies": list(ADOPTED_STRATEGY_BUILDERS), "symbols": SYMBOL_NAMES,
                          "timeframes": ENTRY_TIMEFRAMES, "results": {}}

    t_start = time.time()
    for strategy_name in ADOPTED_STRATEGY_BUILDERS:
        all_results["results"][strategy_name] = {}
        for symbol_name in SYMBOL_NAMES:
            all_results["results"][strategy_name][symbol_name] = {}
            for tf_name in ENTRY_TIMEFRAMES:
                result = run_one(strategy_name, symbol_name, tf_name, session_defs)
                all_results["results"][strategy_name][symbol_name][tf_name] = result

                out_path = Path("data/optimization_results/m1_full_backtest.json")
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(json.dumps(all_results, indent=2, default=str))

    total_elapsed = time.time() - t_start
    print(f"\n=== ALL RUNS COMPLETE in {total_elapsed / 60:.1f} minutes ===", flush=True)
    print("summary written to data/optimization_results/m1_full_backtest.json", flush=True)


if __name__ == "__main__":
    main()
