"""Point-in-Time helpers for the Backtesting Engine.

The single rule this module exists to enforce: at simulated time `as_of`,
nothing downstream may see a candle that closes after `as_of`. All slicing
goes through CandleSeries.sliced_as_of so there is exactly one place this
logic can go wrong.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.market_data.models import CandleSeries


def get_data_as_of(series: CandleSeries, as_of: datetime) -> CandleSeries:
    return series.sliced_as_of(as_of)


@dataclass
class BacktestClock:
    """Tracks 'now' as the engine steps forward bar by bar."""
    current_time: datetime

    def advance_to(self, timestamp: datetime) -> None:
        if timestamp < self.current_time:
            raise ValueError("backtest clock cannot move backwards")
        self.current_time = timestamp
