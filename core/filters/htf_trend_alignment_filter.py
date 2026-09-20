"""HTFTrendAlignmentFilter — rejects a signal whose direction conflicts
with the Higher Timeframe's own trend.

Addresses research spec section 13 (Multi-Timeframe): AnalysisContext has
always carried a `higher_timeframe` series (H4, by config), but a direct
check found NONE of Classic/SMC/ICT/sweep_displacement/session_breakout
actually reads it — every one of them makes its decision purely from
`entry_timeframe`. The three-timeframe architecture (Higher = trend/
structure, Middle = setup, Entry = trigger) has always existed as
plumbing without behavior behind the Higher role specifically. This is a
real, verified gap (see research/STRATEGY_RESEARCH_REGISTRY.md), not
assumed — and per that section's own instruction, the fix is a testable
CURRENT-vs-MODIFIED filter (matching how VolatilityRegimeFilter was
introduced), not a rewrite of every strategy's entry logic, and not added
"because it sounds logical" without measuring whether it actually helps
Expectancy/OOS/Drawdown/Stability.

Reuses core.algorithms.trend.trend_detection.detect_trend (already used
by ClassicStrategy) on `context.higher_timeframe.candles` — no new trend
definition invented for this filter. A "no clear trend" (ranging, or
insufficient higher-timeframe history) Higher Timeframe reading passes
every signal through unfiltered: this filter only blocks signals that
actively conflict with a CLEAR higher-timeframe trend, never signals that
merely lack higher-timeframe confirmation.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.algorithms.trend.trend_detection import detect_trend
from core.context.analysis_context import AnalysisContext
from core.filters.base import BaseFilter, FilterResult
from core.signals.strategy_signal import StrategySignal


@dataclass(frozen=True)
class HTFTrendAlignmentFilter(BaseFilter):
    name: str = "htf_trend_alignment_filter"

    def apply(self, signal: StrategySignal, context: AnalysisContext) -> FilterResult:
        htf_trend = detect_trend(context.higher_timeframe.candles)
        if htf_trend.direction is None:
            return FilterResult(passed=True, reason="no clear higher-timeframe trend to conflict with")
        if htf_trend.direction != signal.direction:
            return FilterResult(passed=False, reason=f"signal direction conflicts with higher-timeframe {htf_trend.direction.value} trend")
        return FilterResult(passed=True, reason=f"aligned with higher-timeframe {htf_trend.direction.value} trend")
