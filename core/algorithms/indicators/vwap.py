"""Volume Weighted Average Price, cumulative over the given candle window
(callers pass a session-sliced or full window as needed)."""
from __future__ import annotations

from core.market_data.models import Candle


def vwap(candles: list[Candle]) -> list[float | None]:
    result: list[float | None] = [None] * len(candles)
    cum_pv = 0.0
    cum_vol = 0.0
    for i, c in enumerate(candles):
        typical_price = (c.high + c.low + c.close) / 3
        cum_pv += typical_price * c.volume
        cum_vol += c.volume
        result[i] = cum_pv / cum_vol if cum_vol else None
    return result
