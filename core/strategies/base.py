"""BaseStrategy — the contract every Classic/SMC/ICT strategy implements.

A strategy receives only an AnalysisContext (CandleSeries + market state)
and produces zero or one StrategySignal. It must NEVER import MetaTrader5
or any adapter — that dependency direction is enforced by code review and
by keeping strategies physically outside adapters/.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from core.context.analysis_context import AnalysisContext
from core.signals.enums import StrategyCategory
from core.signals.strategy_signal import StrategySignal


class BaseStrategy(ABC):
    strategy_id: str
    category: StrategyCategory
    required_timeframe_roles: tuple[str, ...] = ("higher", "middle", "entry")
    min_lookback_bars: int = 50

    # Declarative parameter schema for future optimization/calibration.
    parameters: dict[str, Any] = {}

    @abstractmethod
    def analyze(self, context: AnalysisContext) -> StrategySignal | None:
        """Return a signal if this strategy sees a valid setup, else None."""
