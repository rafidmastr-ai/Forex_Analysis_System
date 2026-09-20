"""StrategySelectionEngine — the orchestrator.

Runs every enabled strategy against the same AnalysisContext, applies
filters, resolves agreement/conflict between Classic/SMC/ICT, scores the
result with the ConfidenceEngine, and enforces the minimum Risk/Reward
floor. The engine never fabricates a fixed R:R — it only accepts or
rejects whatever the strategies' own technical levels produced.
"""
from __future__ import annotations

from core.confidence.confidence_engine import ConfidenceEngine
from core.context.analysis_context import AnalysisContext
from core.filters.base import BaseFilter
from core.signals.enums import Direction, SetupStatus
from core.signals.selected_setup import SelectedSetup, TimeframeUsed
from core.signals.strategy_signal import StrategySignal
from core.strategies.base import BaseStrategy


class StrategySelectionEngine:
    def __init__(
        self,
        confidence_engine: ConfidenceEngine,
        filters: list[BaseFilter] | None = None,
        min_risk_reward: float = 1.5,
    ):
        self._confidence_engine = confidence_engine
        self._filters = filters or []
        self._min_risk_reward = min_risk_reward

    def run(self, strategies: list[BaseStrategy], context: AnalysisContext) -> SelectedSetup | None:
        raw_signals: list[StrategySignal] = []
        for strategy in strategies:
            signal = strategy.analyze(context)
            if signal is None:
                continue
            if self._passes_filters(signal, context):
                raw_signals.append(signal)

        if not raw_signals:
            return None

        buy_signals = [s for s in raw_signals if s.direction == Direction.BUY]
        sell_signals = [s for s in raw_signals if s.direction == Direction.SELL]

        candidates: list[SelectedSetup] = []
        if buy_signals:
            candidates.append(self._build_setup(buy_signals, sell_signals, context))
        if sell_signals:
            candidates.append(self._build_setup(sell_signals, buy_signals, context))

        candidates.sort(key=lambda c: c.confidence_score, reverse=True)

        for candidate in candidates:
            if candidate.meets_min_risk_reward(self._min_risk_reward):
                return candidate

        if candidates:
            best = candidates[0]
            best.status = SetupStatus.REJECTED_MIN_RR
            return best
        return None

    def _passes_filters(self, signal: StrategySignal, context: AnalysisContext) -> bool:
        adjustment = 0
        for f in self._filters:
            result = f.apply(signal, context)
            if not result.passed:
                return False
            adjustment += result.confidence_adjustment
        signal.raw_score_components["_filter_adjustment"] = adjustment
        return True

    def _build_setup(
        self, same_direction: list[StrategySignal], opposite_direction: list[StrategySignal], context: AnalysisContext
    ) -> SelectedSetup:
        primary, *agreeing = sorted(
            same_direction, key=lambda s: s.raw_score_components.get("base_confidence", 0), reverse=True
        )
        filter_adjustment = int(primary.raw_score_components.get("_filter_adjustment", 0))
        score, label, breakdown = self._confidence_engine.score_group(primary, agreeing, filter_adjustment)

        return SelectedSetup(
            winning_signal=primary,
            agreeing_signals=agreeing,
            conflicting_signals=opposite_direction,
            direction=primary.direction,
            entry=primary.suggested_entry_zone.mid,
            stop_loss=primary.suggested_stop_loss,
            take_profit_1=primary.suggested_take_profit_1,
            take_profit_2=primary.suggested_take_profit_2,
            confidence_score=score,
            confidence_label=label,
            confidence_breakdown=breakdown,
            timeframe_used=TimeframeUsed(
                higher=context.higher_timeframe.timeframe.value,
                middle=context.middle_timeframe.timeframe.value,
                entry=context.entry_timeframe.timeframe.value,
            ),
            status=SetupStatus.SELECTED,
        )
