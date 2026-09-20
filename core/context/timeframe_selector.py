"""TimeframeSelector — resolves Higher/Middle/Entry timeframes internally.

The user never picks a timeframe. This component decides it, driven by
config.timeframes (default_mapping + selection_rules) and, when a rule
calls for it, the symbol's current volatility regime. Callers do a small
first pass to classify volatility (see backend/routers/signals.py and
backtesting/engine.py for the two call sites), then call select() to get
the final timeframes before fetching the full-lookback data.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.algorithms.indicators.atr import atr
from core.algorithms.volatility.volatility import classify_volatility
from core.market_data.models import Candle, Timeframe


def classify_volatility_from_candles(candles: list[Candle]) -> str:
    """Shared by the live /analyze flow and the Backtesting Engine so both
    pick timeframes the same way, from an ATR-relative volatility read."""
    return classify_volatility(atr(candles, period=14))


@dataclass(frozen=True)
class SelectedTimeframes:
    higher: Timeframe
    middle: Timeframe
    entry: Timeframe


class TimeframeSelector:
    def __init__(self, timeframes_config: dict):
        self._default = timeframes_config["default_mapping"]
        self._rules = timeframes_config.get("selection_rules", [])

    def select(self, volatility: str | None = None) -> SelectedTimeframes:
        higher = Timeframe(self._default["higher"])
        middle = Timeframe(self._default["middle"])
        entry = Timeframe(self._default["entry"])

        for rule in self._rules:
            if rule.get("condition") == "high_volatility" and volatility == "high":
                if "higher" in rule:
                    higher = Timeframe(rule["higher"])
                if "middle" in rule:
                    middle = Timeframe(rule["middle"])
                if "entry" in rule:
                    entry = Timeframe(rule["entry"])

        return SelectedTimeframes(higher=higher, middle=middle, entry=entry)
