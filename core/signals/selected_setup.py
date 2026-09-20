"""SelectedSetup — the outcome of comparing all StrategySignals for a run.

Produced by the Strategy Selection Engine + Confidence Engine together.
Holds the final technical levels (dynamic, never a fixed R:R target) plus
full transparency on which strategies agreed or conflicted.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.signals.enums import ConfidenceLabel, Direction, SetupStatus, StrategyCategory
from core.signals.strategy_signal import StrategySignal


@dataclass(frozen=True)
class TimeframeUsed:
    higher: str
    middle: str
    entry: str


@dataclass
class SelectedSetup:
    winning_signal: StrategySignal
    agreeing_signals: list[StrategySignal]
    conflicting_signals: list[StrategySignal]

    direction: Direction
    entry: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float

    confidence_score: int  # 0-100 — a relative confidence score, NOT a win probability
    confidence_label: ConfidenceLabel
    confidence_breakdown: dict[str, bool] = field(default_factory=dict)
    confidence_reasons: list[str] = field(default_factory=list)

    timeframe_used: TimeframeUsed | None = None
    status: SetupStatus = SetupStatus.SELECTED

    @property
    def contributing_signals(self) -> list[StrategySignal]:
        return [self.winning_signal, *self.agreeing_signals]

    @property
    def selected_strategy_display(self) -> str:
        """'Classic' / 'SMC' / 'ICT' if only one contributed, else 'Combination'."""
        categories = {self.winning_signal.category} | {s.category for s in self.agreeing_signals}
        if len(categories) == 1:
            return next(iter(categories)).value
        return "Combination"

    @property
    def risk_reward_tp1(self) -> float:
        risk = abs(self.entry - self.stop_loss)
        reward = abs(self.take_profit_1 - self.entry)
        return reward / risk if risk else 0.0

    @property
    def risk_reward_tp2(self) -> float:
        risk = abs(self.entry - self.stop_loss)
        reward = abs(self.take_profit_2 - self.entry)
        return reward / risk if risk else 0.0

    def meets_min_risk_reward(self, min_risk_reward: float) -> bool:
        """The min R:R from config is a rejection floor, never a forced target.

        A small epsilon absorbs floating-point noise from price-difference
        division (e.g. an exact 1:1.5 setup must not be rejected because it
        computes to 1.4999999999999334).
        """
        return self.risk_reward_tp1 >= min_risk_reward - 1e-9
