"""Candlestick pattern confirmation used by the Classic strategy."""
from __future__ import annotations

from core.market_data.models import Candle


def is_bullish_engulfing(prev: Candle, curr: Candle) -> bool:
    return prev.close < prev.open and curr.close > curr.open and curr.close >= prev.open and curr.open <= prev.close


def is_bearish_engulfing(prev: Candle, curr: Candle) -> bool:
    return prev.close > prev.open and curr.close < curr.open and curr.close <= prev.open and curr.open >= prev.close


def pin_bar_direction(candle: Candle) -> str | None:
    """Returns 'bullish', 'bearish', or None. A pin bar has a small body and
    a long wick on one side (classic rejection candle)."""
    body = abs(candle.close - candle.open)
    candle_range = candle.high - candle.low
    if candle_range <= 0 or body / candle_range > 0.35:
        return None
    upper_wick = candle.high - max(candle.close, candle.open)
    lower_wick = min(candle.close, candle.open) - candle.low
    if lower_wick >= candle_range * 0.6 and lower_wick > upper_wick * 2:
        return "bullish"
    if upper_wick >= candle_range * 0.6 and upper_wick > lower_wick * 2:
        return "bearish"
    return None
