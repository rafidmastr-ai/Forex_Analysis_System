"""Current-version evaluation (NOT an optimization step): a real,
comprehensive backtest of the system exactly as it is officially adopted
right now — no new search, no weight/threshold/filter changes, no
Baseline comparison. This script must not be used to tune anything; it
only measures what already exists.

Mirrors backend/dependencies.py's production wiring exactly:
  - Strategies: Classic, SMC, ICT, SweepDisplacement — each constructed
    with its own shipped DEFAULT_WEIGHTS (Classic/SMC/ICT: the original
    baseline-preserving weights, unchanged since Phase 1; SweepDisplacement:
    the Robust Candidate weights adopted in the Research & Strategy
    Development phase). SessionBreakout is intentionally excluded: it was
    tested and NOT adopted (classified "Candidate", never wired into
    bootstrap.py) — this script evaluates the officially adopted system,
    not everything that was ever built.
  - Filters: [VolatilityRegimeFilter(), HTFTrendAlignmentFilter()], the
    exact list backend/dependencies.py wires into get_selection_engine().
  - min_confidence=None (confidence never gates trades in production
    /analyze — only the optimization framework in scripts/optimize_strategy
    .py sets it, for a completely different purpose).
  - min_risk_reward=1.5, confidence thresholds and agreement bonus taken
    directly from config/settings.backtest.yaml, the same file backend/
    dependencies.py loads under APP_ENV=backtest.

Runs over the FULL available historical window (no Train/Validation/OOS
split — nothing here is being selected FROM the data, so there is no
leakage risk a split would guard against), both symbols, and all 15
non-empty combinations of the 4 adopted strategies (single strategies,
every pair/triple, and the full four-strategy "All" — which is what a
real, unfiltered /analyze call actually runs, since production has no
per-request strategy-subset selector).

Point-in-Time discipline, real historical spread, and the existing
conservative same-candle SL-before-TP rule are all inherited unchanged
from backtesting/engine.py — nothing about outcome simulation is modified
for this evaluation.
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
from core.confidence.confidence_engine import ConfidenceEngine  # noqa: E402
from core.filters.htf_trend_alignment_filter import HTFTrendAlignmentFilter  # noqa: E402
from core.filters.volatility_regime_filter import VolatilityRegimeFilter  # noqa: E402
from core.market_data.models import Timeframe  # noqa: E402
from core.selection.strategy_selection_engine import StrategySelectionEngine  # noqa: E402
from core.strategies.classic.classic_strategy import ClassicStrategy  # noqa: E402
from core.strategies.ict.ict_strategy import ICTStrategy  # noqa: E402
from core.strategies.smc.smc_strategy import SMCStrategy  # noqa: E402
from core.strategies.sweep_displacement.sweep_displacement_strategy import (  # noqa: E402
    SweepDisplacementStrategy,
)
from optimization.extended_metrics import compute_extended_metrics  # noqa: E402
from optimization.registry import ExperimentRecord, OptimizationRegistry  # noqa: E402
from optimization.runner import run_backtest  # noqa: E402
from scripts.data_window import full_window_for  # noqa: E402
from scripts.optimize_strategy import (  # noqa: E402
    DATASET,
    LOOKBACK_BARS,
    TIMEFRAMES_CONFIG,
    _provider,
)

CONFIDENCE_THRESHOLDS = {"weak_max": 49, "medium_max": 74}
AGREEMENT_BONUS = 10
MIN_RISK_REWARD = 1.5

ADOPTED_STRATEGY_BUILDERS = {
    "Classic": ClassicStrategy, "SMC": SMCStrategy, "ICT": ICTStrategy, "SweepDisplacement": SweepDisplacementStrategy,
}
ALL_NAMES = list(ADOPTED_STRATEGY_BUILDERS)


def _all_nonempty_subsets(names: list[str]) -> list[list[str]]:
    subsets = []
    n = len(names)
    for mask in range(1, 1 << n):
        subsets.append([names[i] for i in range(n) if mask & (1 << i)])
    subsets.sort(key=len)
    return subsets


COMBINATIONS = _all_nonempty_subsets(ALL_NAMES)


def _production_selection_engine() -> StrategySelectionEngine:
    """Exactly backend/dependencies.py's get_selection_engine(), reconstructed
    here (rather than imported) because that function is @lru_cache-bound to
    FastAPI's own settings/env wiring; the filter list and thresholds are
    copied verbatim and must be kept in sync if that file changes."""
    confidence_engine = ConfidenceEngine(thresholds=CONFIDENCE_THRESHOLDS, multi_strategy_agreement_bonus=AGREEMENT_BONUS)
    return StrategySelectionEngine(
        confidence_engine=confidence_engine,
        filters=[VolatilityRegimeFilter(), HTFTrendAlignmentFilter()],
        min_risk_reward=MIN_RISK_REWARD,
    )


def _build_strategies(names: list[str]) -> list:
    return [ADOPTED_STRATEGY_BUILDERS[n]() for n in names]


def _combo_label(names: list[str]) -> str:
    return "All" if set(names) == set(ALL_NAMES) else "+".join(names)


SESSION_PRIORITY = ["LondonNewYorkOverlap", "London", "NewYork", "Asian"]


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


def _spread_impact(outcomes, provider, symbol_name: str) -> dict:
    """Discloses, rather than silently corrects, a real modeling
    characteristic: every entry in this system fills at the bid/ask
    MIDPOINT for both BUY and SELL (AnalysisContext.current_price), not at
    ask-for-buy/bid-for-sell as a live broker would fill — a longstanding
    architectural characteristic predating this evaluation, not a new bug,
    and NOT changed here per the explicit instruction not to touch Entry/
    TP/SL during this pass. This computes what an ADDITIONAL one-spread
    round-trip cost (a conservative slippage buffer on top of the current
    convention) would do to Net R, using each trade's REAL historical
    spread — a disclosed sensitivity estimate, not an altered outcome."""
    symbol = provider.get_symbol_info(symbol_name)
    entry_series = provider.get_ohlcv(symbol, Timeframe.M15, count=100000)
    by_ts = {c.timestamp: c for c in entry_series.candles}

    resolved = [o for o in outcomes if o.hit != "NONE"]
    if not resolved:
        return {"trades_with_spread_data": 0}

    spread_costs_in_r = []
    spread_pips = []
    for o in resolved:
        candle = by_ts.get(o.opened_at)
        if candle is None or not candle.spread:
            continue
        risk_distance = abs(o.setup.entry - o.setup.stop_loss)
        if risk_distance <= 0:
            continue
        spread_costs_in_r.append(candle.spread / risk_distance)
        spread_pips.append(candle.spread / symbol.pip_size)

    if not spread_costs_in_r:
        return {"trades_with_spread_data": 0}

    net_r_current = sum(o.r_multiple for o in resolved)
    additional_cost_r = sum(spread_costs_in_r)
    return {
        "trades_with_spread_data": len(spread_costs_in_r),
        "average_spread_pips": sum(spread_pips) / len(spread_pips),
        "average_spread_cost_in_r": sum(spread_costs_in_r) / len(spread_costs_in_r),
        "current_net_r": net_r_current,
        "net_r_if_one_additional_spread_round_trip_charged": net_r_current - additional_cost_r,
        "total_additional_cost_r": additional_cost_r,
    }


def run_symbol(symbol_name: str, registry: OptimizationRegistry) -> dict:
    provider = _provider()
    selection_engine = _production_selection_engine()
    results: dict = {}
    reports: dict = {}
    window = full_window_for(symbol_name)

    for names in COMBINATIONS:
        label = _combo_label(names)
        t0 = time.time()
        strategies = _build_strategies(names)
        report = run_backtest(
            strategies=strategies, provider=provider, selection_engine=selection_engine,
            symbol_name=symbol_name, timeframe=Timeframe.M15, start=window[0], end=window[1],
            timeframes_config=TIMEFRAMES_CONFIG, lookback_bars=LOOKBACK_BARS, min_confidence=None,
        )
        reports[label] = report
        m = compute_extended_metrics(report.outcomes)
        elapsed = time.time() - t0

        rec = ExperimentRecord(
            strategy=label, symbol=symbol_name, timeframe="M15", dataset=DATASET, phase="combination",
            training_period=(window[0].isoformat(), window[1].isoformat()),
            validation_period=("", ""), oos_period=("", ""),
            parameters={"min_confidence": None, "members": names, "purpose": "final_evaluation_current_version"},
            component_weights={}, disabled_components=[],
            trade_count=m.trade_count, resolved_count=m.resolved_count, win_rate=m.win_rate,
            tp1_rate=m.tp1_rate, tp2_rate=m.tp2_rate, sl_rate=m.sl_rate,
            profit_factor=m.profit_factor if m.profit_factor != float("inf") else 999.0,
            net_r=m.net_r, expectancy=m.expectancy, average_r=m.average_r,
            max_drawdown_r=m.max_drawdown_r, instability=0.0,
            composite_objective=0.0, status="Candidate",
            notes="Final current-version evaluation (not an optimization experiment) -- see RESEARCH_AND_STRATEGY_DEVELOPMENT report lineage",
        )
        registry.log(rec)

        results[label] = {"metrics": asdict(m), "elapsed_seconds": elapsed}
        print(f"[{symbol_name}/{label}] trades={m.trade_count} resolved={m.resolved_count} "
              f"win_rate={m.win_rate:.3f} net_r={m.net_r:.2f} pf={m.profit_factor:.2f} ({elapsed:.1f}s)", flush=True)

    all_report = reports["All"]

    by_strategy: dict[str, dict] = {}
    for display in ("Classic", "SMC", "ICT", "Liquidity", "Combination"):
        subset = [o for o in all_report.outcomes if o.setup.selected_strategy_display == display]
        if subset:
            by_strategy[display] = asdict(compute_extended_metrics(subset))

    by_direction: dict[str, dict] = {}
    for direction_name in ("BUY", "SELL"):
        subset = [o for o in all_report.outcomes if o.setup.direction.value == direction_name]
        if subset:
            by_direction[direction_name] = asdict(compute_extended_metrics(subset))

    entry_series = provider.get_ohlcv(provider.get_symbol_info(symbol_name), Timeframe.M15, count=100000)
    timestamps = [c.timestamp for c in entry_series.candles]
    atr_values = atr(entry_series.candles, period=14)
    session_defs = _load_session_defs()

    regime_buckets: dict[str, list] = {}
    session_buckets: dict[str, list] = {}
    for outcome in all_report.resolved_outcomes:
        idx = max(0, bisect.bisect_right(timestamps, outcome.opened_at) - 1)
        regime = classify_volatility(atr_values[: idx + 1])
        session = _session_for(outcome.opened_at, session_defs)
        regime_buckets.setdefault(regime, []).append(outcome)
        session_buckets.setdefault(session, []).append(outcome)

    by_regime = {k: asdict(compute_extended_metrics(v)) for k, v in regime_buckets.items()}
    by_session = {k: asdict(compute_extended_metrics(v)) for k, v in session_buckets.items()}

    spread_impact = _spread_impact(all_report.outcomes, provider, symbol_name)

    print(f"[{symbol_name}/by_strategy] " + ", ".join(f"{k}:{v['trade_count']}" for k, v in by_strategy.items()), flush=True)
    print(f"[{symbol_name}/by_direction] " + ", ".join(f"{k}:{v['trade_count']}" for k, v in by_direction.items()), flush=True)
    print(f"[{symbol_name}/by_regime] " + ", ".join(f"{k}:{v['trade_count']}" for k, v in by_regime.items()), flush=True)
    print(f"[{symbol_name}/by_session] " + ", ".join(f"{k}:{v['trade_count']}" for k, v in by_session.items()), flush=True)
    print(f"[{symbol_name}/spread_impact] {spread_impact}", flush=True)

    return {
        "combinations": results, "by_strategy": by_strategy, "by_direction": by_direction,
        "by_regime": by_regime, "by_session": by_session, "spread_impact": spread_impact,
    }


def main() -> None:
    registry = OptimizationRegistry()
    summary = {
        "purpose": "current-version evaluation (not an optimization step)",
        # Per-symbol, not a single shared window -- symbols are not guaranteed
        # (and, in the current data/market/ upload, are not) identical in range.
        "windows": {s: [w.isoformat() for w in full_window_for(s)] for s in ("EURUSD", "XAUUSD")},
        "adopted_strategies": ALL_NAMES,
        "filters": ["VolatilityRegimeFilter", "HTFTrendAlignmentFilter"],
        "min_confidence": None, "min_risk_reward": MIN_RISK_REWARD,
    }
    for symbol_name in ("EURUSD", "XAUUSD"):
        print(f"=== final evaluation :: {symbol_name} ===", flush=True)
        summary[symbol_name] = run_symbol(symbol_name, registry)

    out_path = Path("data/optimization_results/final_evaluation_summary.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2, default=str))
    print(f"summary written to {out_path}", flush=True)


if __name__ == "__main__":
    main()
