"""Task 37: combination testing — does running Classic+SMC / Classic+ICT /
SMC+ICT / All together add independent information over each strategy
alone, or just duplicate/dilute the same signal? — plus a descriptive
market-regime (volatility) and session breakdown.

This intentionally comes AFTER Task 36 (independent per-strategy weight
optimization) and uses each strategy's shipped DEFAULT_WEIGHTS: Task 36
found no candidate weight set robust enough to adopt for Classic, SMC or
ICT (see data/optimization_results/{classic,smc,ict}_summary.json), so
there are no "optimized" weights to combine here — this answers a
genuinely different question (do the strategies' EXISTING signals overlap
or complement each other) independently of that result.

Uses the same min_confidence=65 filter as Task 36 for consistency, over
the FULL 2025-09-15..2026-09-16 window rather than a Train/Validation/OOS
split — nothing here is being searched or selected FROM the data (no
weights are tuned against these results), so there is no leakage risk to
guard against; this mirrors the descriptive-backtest methodology already
used for data/historical_backtest_results/baseline_results.json (which
this script never modifies).

Regime breakdown is computed only on the "All" (Classic+SMC+ICT) run per
symbol, since it is the most complete trade set — classifying each
resolved trade's opened_at by session (config/settings.backtest.yaml's
UTC session windows) and by ATR-percentile volatility regime (core.
algorithms.volatility.classify_volatility, using only history up to and
including that candle — descriptive labeling of already-decided trades,
not a decision input, so no look-ahead concern).
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
from core.market_data.models import Timeframe  # noqa: E402
from core.strategies.classic.classic_strategy import ClassicStrategy  # noqa: E402
from core.strategies.ict.ict_strategy import ICTStrategy  # noqa: E402
from core.strategies.smc.smc_strategy import SMCStrategy  # noqa: E402
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

STRATEGY_BUILDERS = {"Classic": ClassicStrategy, "SMC": SMCStrategy, "ICT": ICTStrategy}
COMBINATIONS = [
    ["Classic"], ["SMC"], ["ICT"],
    ["Classic", "SMC"], ["Classic", "ICT"], ["SMC", "ICT"],
    ["Classic", "SMC", "ICT"],
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
    return "+".join(names) if len(names) < 3 else "All"


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
        for display in ("Classic", "SMC", "ICT", "Combination"):
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


def main() -> None:
    registry = OptimizationRegistry()
    summary = {"min_confidence": MIN_CONFIDENCE, "window": [FULL_WINDOW[0].isoformat(), FULL_WINDOW[1].isoformat()]}
    for symbol_name in ("EURUSD", "XAUUSD"):
        print(f"=== combinations :: {symbol_name} ===", flush=True)
        summary[symbol_name] = run_symbol(symbol_name, registry)

    out_path = Path("data/optimization_results/combinations_summary.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2, default=str))
    print(f"summary written to {out_path}", flush=True)


if __name__ == "__main__":
    main()
