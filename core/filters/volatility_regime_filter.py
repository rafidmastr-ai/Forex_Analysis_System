"""VolatilityRegimeFilter — rejects a signal when the entry timeframe's
current ATR-percentile volatility regime is "high".

Evidence, not opinion: our own Task-37 combination-testing pass
(data/optimization_results/combinations_summary.json) found "high"
volatility to be the worst-performing regime on BOTH EURUSD and XAUUSD
under the current strategies (EURUSD high-vol objective -40.5 vs low-vol
-17.3; XAUUSD high-vol objective -41.5 with net R -36.05 vs low-vol +56.25
net R). This is also consistent with the published FX microstructure
literature on session/volatility (Andersen & Bollerslev 1998; Dacorogna et
al. 2001) showing volatility clusters around specific liquidity windows
rather than arriving uniformly — see research/STRATEGY_RESEARCH_REGISTRY.md
entry SRR-004. This filter operationalizes that finding as a testable
CURRENT-vs-MODIFIED comparison (research spec §3/§4): it is never applied
inside a strategy's own `analyze()`, only wired in externally via
StrategySelectionEngine(filters=[...]) so its effect can be measured
independently per strategy, per research spec.

Uses core.algorithms.volatility.classify_volatility, the same ATR-
percentile classifier already used for the Task-37 regime breakdown and
for TimeframeSelector's high-volatility rule — no new volatility
definition invented for this filter.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.algorithms.indicators.atr import atr
from core.algorithms.volatility.volatility import classify_volatility
from core.context.analysis_context import AnalysisContext
from core.filters.base import BaseFilter, FilterResult
from core.signals.strategy_signal import StrategySignal


@dataclass(frozen=True)
class VolatilityRegimeFilter(BaseFilter):
    name: str = "volatility_regime_filter"
    reject_regimes: frozenset[str] = frozenset({"high"})
    atr_period: int = 14

    def apply(self, signal: StrategySignal, context: AnalysisContext) -> FilterResult:
        candles = context.entry_timeframe.candles
        atr_values = atr(candles, period=self.atr_period)
        regime = classify_volatility(atr_values)
        if regime in self.reject_regimes:
            return FilterResult(passed=False, reason=f"volatility regime '{regime}' is filtered out")
        return FilterResult(passed=True, reason=f"volatility regime '{regime}' accepted")
