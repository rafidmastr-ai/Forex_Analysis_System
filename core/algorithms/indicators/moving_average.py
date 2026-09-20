"""Simple/Exponential moving averages over closing prices."""
from __future__ import annotations

from core.market_data.models import Candle


def sma(candles: list[Candle], period: int) -> list[float | None]:
    closes = [c.close for c in candles]
    result: list[float | None] = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        result[i] = sum(closes[i - period + 1: i + 1]) / period
    return result


def ema(candles: list[Candle], period: int) -> list[float | None]:
    closes = [c.close for c in candles]
    result: list[float | None] = [None] * len(closes)
    if len(closes) < period:
        return result
    multiplier = 2 / (period + 1)
    seed = sum(closes[:period]) / period
    result[period - 1] = seed
    prev = seed
    for i in range(period, len(closes)):
        prev = (closes[i] - prev) * multiplier + prev
        result[i] = prev
    return result
