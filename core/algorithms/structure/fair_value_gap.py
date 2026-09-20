"""Fair Value Gap (FVG) — a 3-candle imbalance where the wicks of candle[i-1]
and candle[i+1] don't overlap, leaving a gap price is statistically likely
to revisit. Used by both SMC and ICT."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.market_data.models import Candle
from core.signals.enums import Direction
from core.signals.strategy_signal import PriceZone


@dataclass(frozen=True)
class FVGZone:
    direction: Direction  # BUY = bullish FVG (support gap), SELL = bearish FVG (resistance gap)
    zone: PriceZone
    index: int  # index of the middle candle
    timestamp: datetime


def find_fair_value_gaps(candles: list[Candle]) -> list[FVGZone]:
    gaps: list[FVGZone] = []
    for i in range(1, len(candles) - 1):
        left, mid, right = candles[i - 1], candles[i], candles[i + 1]
        if right.low > left.high:
            gaps.append(FVGZone(direction=Direction.BUY, zone=PriceZone(low=left.high, high=right.low),
                                 index=i, timestamp=mid.timestamp))
        elif right.high < left.low:
            gaps.append(FVGZone(direction=Direction.SELL, zone=PriceZone(low=right.high, high=left.low),
                                 index=i, timestamp=mid.timestamp))
    return gaps
