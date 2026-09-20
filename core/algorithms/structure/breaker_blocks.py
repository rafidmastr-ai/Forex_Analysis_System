"""Breaker Blocks — an Order Block that later gets invalidated (price
closes through its far side) flips role: a broken bearish OB becomes
bullish support, a broken bullish OB becomes bearish resistance.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.algorithms.structure.order_blocks import OrderBlock
from core.market_data.models import Candle
from core.signals.enums import Direction
from core.signals.strategy_signal import PriceZone


@dataclass(frozen=True)
class BreakerBlock:
    direction: Direction  # the NEW role after the flip
    zone: PriceZone
    timestamp: datetime
    index: int
    source_order_block_index: int


def find_breaker_blocks(candles: list[Candle], order_blocks: list[OrderBlock]) -> list[BreakerBlock]:
    breakers: list[BreakerBlock] = []
    for ob in order_blocks:
        for j in range(ob.index + 1, len(candles)):
            candle = candles[j]
            if ob.direction == Direction.SELL and candle.close > ob.zone.high:
                breakers.append(BreakerBlock(direction=Direction.BUY, zone=ob.zone, timestamp=candle.timestamp,
                                              index=j, source_order_block_index=ob.index))
                break
            if ob.direction == Direction.BUY and candle.close < ob.zone.low:
                breakers.append(BreakerBlock(direction=Direction.SELL, zone=ob.zone, timestamp=candle.timestamp,
                                              index=j, source_order_block_index=ob.index))
                break
    return breakers
