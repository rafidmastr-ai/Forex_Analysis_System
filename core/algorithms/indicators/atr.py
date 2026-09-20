"""Average True Range — the shared volatility measure used for SL distance
and displacement detection."""
from __future__ import annotations

from core.market_data.models import Candle


def true_range(curr: Candle, prev: Candle | None) -> float:
    if prev is None:
        return curr.high - curr.low
    return max(
        curr.high - curr.low,
        abs(curr.high - prev.close),
        abs(curr.low - prev.close),
    )


def atr(candles: list[Candle], period: int = 14) -> list[float | None]:
    trs: list[float] = [true_range(c, candles[i - 1] if i > 0 else None) for i, c in enumerate(candles)]
    result: list[float | None] = [None] * len(candles)
    if len(candles) < period:
        return result
    seed = sum(trs[:period]) / period
    result[period - 1] = seed
    prev = seed
    for i in range(period, len(candles)):
        prev = (prev * (period - 1) + trs[i]) / period
        result[i] = prev
    return result
