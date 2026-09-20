"""Swing high/low detection (fractals) — the base primitive every structure
algorithm (BOS/CHoCH, order blocks, liquidity, premium/discount) builds on.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.market_data.models import Candle


@dataclass(frozen=True)
class SwingPoint:
    index: int
    timestamp: datetime
    price: float
    kind: str  # "high" | "low"


def find_swing_points(candles: list[Candle], lookback: int = 2) -> list[SwingPoint]:
    """A candle at index i is a swing high if its high is the strictest max
    among the `lookback` candles on each side (and symmetrically for lows).
    """
    swings: list[SwingPoint] = []
    n = len(candles)
    for i in range(lookback, n - lookback):
        window = candles[i - lookback: i + lookback + 1]
        candle = candles[i]
        if candle.high == max(c.high for c in window) and _is_unique_max(window, i - (i - lookback)):
            swings.append(SwingPoint(index=i, timestamp=candle.timestamp, price=candle.high, kind="high"))
        if candle.low == min(c.low for c in window) and _is_unique_min(window, i - (i - lookback)):
            swings.append(SwingPoint(index=i, timestamp=candle.timestamp, price=candle.low, kind="low"))
    return swings


def _is_unique_max(window: list[Candle], center_offset: int) -> bool:
    highs = [c.high for c in window]
    return highs.count(highs[center_offset]) == 1


def _is_unique_min(window: list[Candle], center_offset: int) -> bool:
    lows = [c.low for c in window]
    return lows.count(lows[center_offset]) == 1
