"""Task 45 (+ HTF extension, spec section 13): CURRENT vs MODIFIED test of
a single cross-cutting Filter, per the research spec's explicit "compare
CURRENT vs MODIFIED, don't just add a filter because it sounds sensible"
requirement (section 3/4/13).

Unlike scripts/optimize_strategy.py, this does NOT set min_confidence —
these are real, production-shaped filters (wired through
StrategySelectionEngine's `filters` list, the same mechanism /analyze
itself would use), not optimization-only search knobs. So CURRENT here
means "what /analyze actually does today" (each strategy's own shipped
DEFAULT_WEIGHTS, no confidence floor, no extra filter) and MODIFIED means
the same setup with the ONE filter under test added — isolating exactly
one variable at a time (running both filters together would answer a
different, combined question, not asked for here).

Evaluated across every strategy currently in the project (Classic, SMC,
ICT, sweep_displacement, session_breakout), both symbols, and the same
reused Train/Validation/OOS split as every other experiment in this
phase — never a new split chosen to flatter this specific idea.

Usage: python scripts/test_volatility_filter.py [volatility|htf]
(defaults to volatility for backwards compatibility with Task 45's
original invocation).
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.confidence.confidence_engine import ConfidenceEngine  # noqa: E402
from core.filters.base import BaseFilter  # noqa: E402
from core.filters.htf_trend_alignment_filter import HTFTrendAlignmentFilter  # noqa: E402
from core.filters.volatility_regime_filter import VolatilityRegimeFilter  # noqa: E402
from core.market_data.models import Timeframe  # noqa: E402
from core.selection.strategy_selection_engine import StrategySelectionEngine  # noqa: E402
from optimization.objective import composite_objective, compute_metrics  # noqa: E402
from optimization.registry import ExperimentRecord, OptimizationRegistry  # noqa: E402
from optimization.runner import run_backtest  # noqa: E402
from scripts.optimize_strategy import (  # noqa: E402
    DATASET,
    FULL_WINDOW,
    LOOKBACK_BARS,
    STRATEGY_SPECS,
    TIMEFRAMES_CONFIG,
    _provider,
    chronological_split,
)

CONFIDENCE_THRESHOLDS = {"weak_max": 49, "medium_max": 74}
AGREEMENT_BONUS = 10

FILTERS: dict[str, tuple[list[BaseFilter], str]] = {
    "volatility": ([VolatilityRegimeFilter()], "MODIFIED_volatility_filter"),
    "htf": ([HTFTrendAlignmentFilter()], "MODIFIED_htf_trend_alignment_filter"),
    "both": ([VolatilityRegimeFilter(), HTFTrendAlignmentFilter()], "MODIFIED_both_filters"),
}


def _selection_engine(filters: list[BaseFilter]) -> StrategySelectionEngine:
    confidence_engine = ConfidenceEngine(thresholds=CONFIDENCE_THRESHOLDS, multi_strategy_agreement_bonus=AGREEMENT_BONUS)
    return StrategySelectionEngine(confidence_engine=confidence_engine, filters=filters, min_risk_reward=1.5)


def _evaluate(strategy_key: str, symbol: str, filters: list[BaseFilter], start, end):
    spec = STRATEGY_SPECS[strategy_key]
    strategy = spec["cls"](weights=spec["cls"].DEFAULT_WEIGHTS)
    report = run_backtest(
        strategies=[strategy], provider=_provider(), selection_engine=_selection_engine(filters),
        symbol_name=symbol, timeframe=Timeframe.M15, start=start, end=end,
        timeframes_config=TIMEFRAMES_CONFIG, lookback_bars=LOOKBACK_BARS, min_confidence=None,
    )
    return compute_metrics(report.outcomes)


def main(filter_key: str) -> None:
    filters, modified_label = FILTERS[filter_key]
    registry = OptimizationRegistry()
    split = chronological_split(*FULL_WINDOW)
    results: dict = {}

    for strategy_key in STRATEGY_SPECS:
        strategy_id = STRATEGY_SPECS[strategy_key]["cls"].strategy_id
        results[strategy_key] = {}
        for symbol in ("EURUSD", "XAUUSD"):
            results[strategy_key][symbol] = {}
            for phase, (start, end) in (("train", split.train), ("validation", split.validation), ("out_of_sample", split.out_of_sample)):
                t0 = time.time()
                current = _evaluate(strategy_key, symbol, [], start, end)
                modified = _evaluate(strategy_key, symbol, filters, start, end)
                current_obj = composite_objective(current)
                modified_obj = composite_objective(modified)
                elapsed = time.time() - t0

                for label, metrics, obj in (("CURRENT", current, current_obj), (modified_label, modified, modified_obj)):
                    rec = ExperimentRecord(
                        strategy=f"{strategy_id}+{label}", symbol=symbol, timeframe="M15", dataset=DATASET, phase=phase,
                        training_period=(split.train[0].isoformat(), split.train[1].isoformat()),
                        validation_period=(split.validation[0].isoformat(), split.validation[1].isoformat()),
                        oos_period=(split.out_of_sample[0].isoformat(), split.out_of_sample[1].isoformat()),
                        parameters={"min_confidence": None, "filter": label},
                        component_weights={}, disabled_components=[],
                        trade_count=metrics.trade_count, resolved_count=metrics.resolved_count, win_rate=metrics.win_rate,
                        tp1_rate=metrics.tp1_rate, tp2_rate=metrics.tp2_rate, sl_rate=metrics.sl_rate,
                        profit_factor=metrics.profit_factor if metrics.profit_factor != float("inf") else 999.0,
                        net_r=metrics.net_r, expectancy=metrics.expectancy, average_r=metrics.average_r,
                        max_drawdown_r=metrics.max_drawdown_r, instability=metrics.instability,
                        composite_objective=obj, status="Candidate",
                        notes=f"CURRENT vs {modified_label} comparison",
                    )
                    registry.log(rec)

                results[strategy_key][symbol][phase] = {
                    "current": {"metrics": asdict(current), "objective": current_obj},
                    "modified": {"metrics": asdict(modified), "objective": modified_obj},
                    "delta_objective": modified_obj - current_obj,
                }
                print(f"[{strategy_key}/{symbol}/{phase}] CURRENT obj={current_obj:.3f} (n={current.resolved_count}) "
                      f"-> MODIFIED obj={modified_obj:.3f} (n={modified.resolved_count}) delta={modified_obj - current_obj:+.3f} "
                      f"({elapsed:.1f}s)", flush=True)

    out_path = Path("data/optimization_results") / f"{filter_key}_filter_comparison.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"summary written to {out_path}", flush=True)


if __name__ == "__main__":
    key = sys.argv[1] if len(sys.argv) > 1 else "volatility"
    if key not in FILTERS:
        print(f"usage: python {sys.argv[0]} <{'|'.join(FILTERS)}>")
        sys.exit(1)
    main(key)
