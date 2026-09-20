"""Order Block detection: the last opposite-direction candle before the
impulsive move that produced a confirmed structure break (BOS/CHoCH)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.algorithms.structure.market_structure import StructureEvent
from core.market_data.models import Candle
from core.signals.enums import Direction
from core.signals.strategy_signal import PriceZone


@dataclass(frozen=True)
class OrderBlock:
    direction: Direction  # BUY = bullish/demand block, SELL = bearish/supply block
    zone: PriceZone
    timestamp: datetime
    index: int
    structure_event_index: int


def find_order_blocks(candles: list[Candle], structure_events: list[StructureEvent], lookback: int = 10) -> list[OrderBlock]:
    blocks: list[OrderBlock] = []
    for event in structure_events:
        start = max(0, event.index - lookback)
        for j in range(event.index - 1, start - 1, -1):
            candle = candles[j]
            is_bearish = candle.close < candle.open
            is_bullish = candle.close > candle.open
            if event.direction == Direction.BUY and is_bearish:
                blocks.append(OrderBlock(direction=Direction.BUY, zone=PriceZone(low=candle.low, high=candle.high),
                                          timestamp=candle.timestamp, index=j, structure_event_index=event.index))
                break
            if event.direction == Direction.SELL and is_bullish:
                blocks.append(OrderBlock(direction=Direction.SELL, zone=PriceZone(low=candle.low, high=candle.high),
                                          timestamp=candle.timestamp, index=j, structure_event_index=event.index))
                break
    return blocks
