"""Task 37 (+ Task 46 extension): combination testing — does running
strategies together add independent information over each alone, or just
duplicate/dilute the same signal? — plus a descriptive market-regime
(volatility) and session breakdown, plus a raw-signal independence /
correlation check between every strategy pair.

This intentionally comes AFTER Task 36/44 (independent per-strategy weight
optimization) and uses each strategy's shipped DEFAULT_WEIGHTS: no
"optimized" weights are combined here that weren't already separately
validated — this answers a genuinely different question (do the
strategies' EXISTING signals overlap or complement each other).

Task 46 extends the original Classic/SMC/ICT-only combination set (kept
here rather than duplicated — their DEFAULT_WEIGHTS haven't changed since
Task 37, so re-running them would reproduce identical numbers) with the
two Research & Strategy Development phase additions, sweep_displacement
and session_breakout: each alone, each existing strategy paired with each
new one, and the full 5-strategy "All" combination -- 12 configurations,
not an exhaustive 31-subset combinatorial explosion.

Uses the same min_confidence=65 filter as Task 36 for consistency, over
the FULL 2025-09-15..2026-09-16 window rather than a Train/Validation/OOS
split — nothing here is being searched or selected FROM the data (no
weights are tuned against these results), so there is no leakage risk to
guard against; this mirrors the descriptive-backtest methodology already
used for data/historical_backtest_results/baseline_results.json (which
this script never modifies).

Regime breakdown is computed only on the "All" (all 5 strategies) run per
symbol, since it is the most complete trade set — classifying each
resolved trade's opened_at by session (config/settings.backtest.yaml's
UTC session windows) and by ATR-percentile volatility regime (core.
algorithms.volatility.classify_volatility, using only history up to and
including that candle — descriptive labeling of already-decided trades,
not a decision input, so no look-ahead concern).

Independence check (Task 46, spec section 14: "if strategies give the
same signal from the same information, don't count them as independent
evidence"): for every strategy pair, scans the RAW analyze() output (no
selection engine, no filters, no confidence/RR floor — the underlying
technical signal itself) across the full window and computes how often
both strategies fire on the same candle, and when they do, how often they
agree on direction. High overlap + high agreement = duplicated evidence;
low overlap = genuinely independent information sources.
"""
from __future__ import annotations

import bisect
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from datetime import time as dt_time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.algorithms.indicators.atr import atr  # noqa: E402
from core.algorithms.volatility.volatility import classify_volatility  # noqa: E402
from core.context.analysis_context import AnalysisContext  # noqa: E402
from core.market_data.models import Timeframe  # noqa: E402
from core.strategies.classic.classic_strategy import ClassicStrategy  # noqa: E402
from core.strategies.ict.ict_strategy import ICTStrategy  # noqa: E402
from core.strategies.session_breakout.session_breakout_strategy import (  # noqa: E402
    SessionBreakoutStrategy,
)
from core.strategies.smc.smc_strategy import SMCStrategy  # noqa: E402
from core.strategies.sweep_displacement.sweep_displacement_strategy import (  # noqa: E402
    SweepDisplacementStrategy,
)
from optimization.objective import composite_objective, compute_metrics  # noqa: E402
from optimization.registry import ExperimentRecord, OptimizationRegistry  # noqa: E402
from optimization.runner import run_backtest  # noqa: E402
from scripts.optimize_strategy import (  # noqa: E402
    DATASET,
    FULL_WINDOW,
    LOOKBACK_BARS,
    MIN_CONFIDENCE,
    TIMEFRAMES_CONFIG,
    _provider,
    _selection_engine,
)

SESSION_PRIORITY = ["LondonNewYorkOverlap", "London", "NewYork", "Asian"]

STRATEGY_BUILDERS = {
    "Classic": ClassicStrategy, "SMC": SMCStrategy, "ICT": ICTStrategy,
    "SweepDisplacement": SweepDisplacementStrategy, "SessionBreakout": SessionBreakoutStrategy,
}
ALL_STRATEGY_NAMES = list(STRATEGY_BUILDERS)
COMBINATIONS = [
    ["Classic"], ["SMC"], ["ICT"], ["SweepDisplacement"], ["SessionBreakout"],
    ["Classic", "SweepDisplacement"], ["Classic", "SessionBreakout"],
    ["SMC", "SweepDisplacement"], ["SMC", "SessionBreakout"],
    ["ICT", "SweepDisplacement"], ["ICT", "SessionBreakout"],
    ALL_STRATEGY_NAMES,
]


def _parse_hhmm(s: str) -> dt_time:
    h, m = s.split(":")
    return dt_time(int(h), int(m))


def _load_session_defs() -> dict[str, tuple[dt_time, dt_time]]:
    import yaml

    raw = yaml.safe_load(Path("config/settings.backtest.yaml").read_text())
    return {name: (_parse_hhmm(win["start_utc"]), _parse_hhmm(win["end_utc"])) for name, win in raw["session"]["definitions"].items()}


def _session_for(ts: datetime, defs: dict[str, tuple[dt_time, dt_time]]) -> str:
    t = ts.astimezone(timezone.utc).time()
    matches = {name for name, (start, end) in defs.items() if start <= t <= end}
    for name in SESSION_PRIORITY:
        if name in matches:
            return name
    return next(iter(matches), "unspecified")


def _build_strategies(names: list[str]) -> list:
    return [STRATEGY_BUILDERS[n]() for n in names]


def _combo_label(names: list[str]) -> str:
    return "All" if set(names) == set(ALL_STRATEGY_NAMES) else "+".join(names)


def run_symbol(symbol_name: str, registry: OptimizationRegistry) -> dict:
    provider = _provider()
    selection_engine = _selection_engine()
    results = {}
    reports = {}

    for names in COMBINATIONS:
        label = _combo_label(names)
        t0 = time.time()
        strategies = _build_strategies(names)
        report = run_backtest(
            strategies=strategies, provider=provider, selection_engine=selection_engine,
            symbol_name=symbol_name, timeframe=Timeframe.M15, start=FULL_WINDOW[0], end=FULL_WINDOW[1],
            timeframes_config=TIMEFRAMES_CONFIG, lookback_bars=LOOKBACK_BARS, min_confidence=MIN_CONFIDENCE,
        )
        reports[label] = report
        overall = compute_metrics(report.outcomes)
        overall_obj = composite_objective(overall)

        by_display: dict[str, dict] = {}
        for display in ("Classic", "SMC", "ICT", "Liquidity", "Breakout", "Combination"):
            subset = [o for o in report.outcomes if o.setup.selected_strategy_display == display]
            if not subset:
                continue
            m = compute_metrics(subset)
            by_display[display] = {"count": len(subset), "metrics": asdict(m), "objective": composite_objective(m)}

        rec = ExperimentRecord(
            strategy=label, symbol=symbol_name, timeframe="M15", dataset=DATASET, phase="combination",
            training_period=(FULL_WINDOW[0].isoformat(), FULL_WINDOW[1].isoformat()),
            validation_period=("", ""), oos_period=("", ""),
            parameters={"min_confidence": MIN_CONFIDENCE, "members": names},
            component_weights={}, disabled_components=[],
            trade_count=overall.trade_count, resolved_count=overall.resolved_count, win_rate=overall.win_rate,
            tp1_rate=overall.tp1_rate, tp2_rate=overall.tp2_rate, sl_rate=overall.sl_rate,
            profit_factor=overall.profit_factor if overall.profit_factor != float("inf") else 999.0,
            net_r=overall.net_r, expectancy=overall.expectancy, average_r=overall.average_r,
            max_drawdown_r=overall.max_drawdown_r, instability=overall.instability,
            composite_objective=overall_obj, status="Candidate",
            notes=f"combination test, members={names}, by_selected_strategy={ {k: v['count'] for k, v in by_display.items()} }",
        )
        registry.log(rec)

        elapsed = time.time() - t0
        results[label] = {
            "members": names, "overall_metrics": asdict(overall), "overall_objective": overall_obj,
            "by_selected_strategy": by_display, "elapsed_seconds": elapsed,
        }
        print(f"[{symbol_name}/{label}] resolved={overall.resolved_count} net_r={overall.net_r:.2f} "
              f"obj={overall_obj:.3f} by_strategy={ {k: v['count'] for k, v in by_display.items()} } ({elapsed:.1f}s)", flush=True)

    # --- Regime breakdown on the "All" run only ---
    all_report = reports["All"]
    session_defs = _load_session_defs()
    entry_series = provider.get_ohlcv(provider.get_symbol_info(symbol_name), Timeframe.M15, count=100000)
    timestamps = [c.timestamp for c in entry_series.candles]
    atr_values = atr(entry_series.candles, period=14)

    regime_buckets: dict[str, list] = {}
    session_buckets: dict[str, list] = {}
    for outcome in all_report.resolved_outcomes:
        idx = bisect.bisect_right(timestamps, outcome.opened_at) - 1
        idx = max(0, idx)
        regime = classify_volatility(atr_values[: idx + 1])
        session = _session_for(outcome.opened_at, session_defs)
        regime_buckets.setdefault(regime, []).append(outcome)
        session_buckets.setdefault(session, []).append(outcome)

    regime_breakdown = {
        regime: {"count": len(outs), "metrics": asdict(compute_metrics(outs)), "objective": composite_objective(compute_metrics(outs))}
        for regime, outs in regime_buckets.items()
    }
    session_breakdown = {
        session: {"count": len(outs), "metrics": asdict(compute_metrics(outs)), "objective": composite_objective(compute_metrics(outs))}
        for session, outs in session_buckets.items()
    }
    print(f"[{symbol_name}/regime] " + ", ".join(f"{k}:{v['count']}" for k, v in regime_breakdown.items()), flush=True)
    print(f"[{symbol_name}/session] " + ", ".join(f"{k}:{v['count']}" for k, v in session_breakdown.items()), flush=True)

    return {"combinations": results, "regime_breakdown": regime_breakdown, "session_breakdown": session_breakdown}


def _raw_signal_events(symbol_name: str) -> dict[str, dict]:
    """Raw analyze() firing events per strategy — no selection engine, no
    filters, no confidence/RR floor, just "did this strategy see a valid
    setup on this candle, and which direction." This is the correct level
    for an independence check per spec section 14: whether the SELECTION
    engine later merges/picks between them is a separate question from
    whether the underlying technical signals are actually different
    information."""
    provider = _provider()
    symbol = provider.get_symbol_info(symbol_name)
    entry_series = provider.get_ohlcv(symbol, Timeframe.M15, count=100000)
    higher_series = provider.get_ohlcv(symbol, Timeframe.H4, count=100000)
    middle_series = provider.get_ohlcv(symbol, Timeframe.H1, count=100000)

    strategies = {name: cls() for name, cls in STRATEGY_BUILDERS.items()}
    events: dict[str, dict] = {name: {} for name in strategies}

    window = [c for c in entry_series.candles if FULL_WINDOW[0] <= c.timestamp <= FULL_WINDOW[1]]
    for candle in window:
        as_of = candle.timestamp
        context = AnalysisContext(
            symbol=symbol, current_bid=candle.close, current_ask=candle.close + (candle.spread or 0.0),
            session="unspecified",
            higher_timeframe=higher_series.sliced_as_of(as_of), middle_timeframe=middle_series.sliced_as_of(as_of),
            entry_timeframe=entry_series.sliced_as_of(as_of), as_of=as_of,
        )
        for name, strategy in strategies.items():
            signal = strategy.analyze(context)
            if signal is not None:
                events[name][as_of] = signal.direction
    return events


def independence_check(symbol_name: str) -> dict:
    events = _raw_signal_events(symbol_name)
    pairs = {}
    names = list(events)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            fires_a, fires_b = events[a], events[b]
            overlap = fires_a.keys() & fires_b.keys()
            union = fires_a.keys() | fires_b.keys()
            agree = sum(1 for ts in overlap if fires_a[ts] == fires_b[ts])
            jaccard = len(overlap) / len(union) if union else 0.0
            agreement_rate = agree / len(overlap) if overlap else 0.0
            pairs[f"{a}+{b}"] = {
                "fires_a": len(fires_a), "fires_b": len(fires_b), "overlap": len(overlap),
                "jaccard": jaccard, "direction_agreement_rate_when_overlapping": agreement_rate,
            }
    return pairs


def main() -> None:
    registry = OptimizationRegistry()
    summary = {"min_confidence": MIN_CONFIDENCE, "window": [FULL_WINDOW[0].isoformat(), FULL_WINDOW[1].isoformat()]}
    for symbol_name in ("EURUSD", "XAUUSD"):
        print(f"=== combinations :: {symbol_name} ===", flush=True)
        summary[symbol_name] = run_symbol(symbol_name, registry)

        print(f"=== independence check :: {symbol_name} ===", flush=True)
        pairs = independence_check(symbol_name)
        summary[symbol_name]["independence_check"] = pairs
        for pair_label, stats in pairs.items():
            print(f"  {pair_label}: fires={stats['fires_a']}/{stats['fires_b']} overlap={stats['overlap']} "
                  f"jaccard={stats['jaccard']:.3f} agree_when_overlap={stats['direction_agreement_rate_when_overlapping']:.2f}", flush=True)

    out_path = Path("data/optimization_results/combinations_summary.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2, default=str))
    print(f"summary written to {out_path}", flush=True)


if __name__ == "__main__":
    main()
