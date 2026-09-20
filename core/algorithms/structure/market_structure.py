"""Break of Structure (BOS) and Change of Character (CHoCH) detection.

Shared primitive for SMC and ICT (and available to Classic for general
trend-structure context). A close beyond the last confirmed swing level:
  * in the direction of the prevailing trend -> BOS (continuation)
  * against the prevailing trend             -> CHoCH (possible reversal)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.algorithms.structure.swings import SwingPoint
from core.market_data.models import Candle
from core.signals.enums import Direction


@dataclass(frozen=True)
class StructureEvent:
    kind: str  # "BOS" | "CHoCH"
    direction: Direction
    timestamp: datetime
    price: float
    broken_level: float
    index: int


def detect_structure_events(candles: list[Candle], swings: list[SwingPoint]) -> list[StructureEvent]:
    events: list[StructureEvent] = []
    swings_by_index: dict[int, SwingPoint] = {s.index: s for s in swings}

    trend: Direction | None = None
    last_swing_high: SwingPoint | None = None
    last_swing_low: SwingPoint | None = None

    for i, candle in enumerate(candles):
        swing = swings_by_index.get(i)
        if swing is not None:
            if swing.kind == "high":
                last_swing_high = swing
            else:
                last_swing_low = swing

        if last_swing_high is not None and candle.close > last_swing_high.price:
            kind = "BOS" if trend == Direction.BUY else "CHoCH"
            events.append(StructureEvent(kind=kind, direction=Direction.BUY, timestamp=candle.timestamp,
                                          price=candle.close, broken_level=last_swing_high.price, index=i))
            trend = Direction.BUY
            last_swing_high = None
        elif last_swing_low is not None and candle.close < last_swing_low.price:
            kind = "BOS" if trend == Direction.SELL else "CHoCH"
            events.append(StructureEvent(kind=kind, direction=Direction.SELL, timestamp=candle.timestamp,
                                          price=candle.close, broken_level=last_swing_low.price, index=i))
            trend = Direction.SELL
            last_swing_low = None

    return events


def latest_trend(events: list[StructureEvent]) -> Direction | None:
    return events[-1].direction if events else None
