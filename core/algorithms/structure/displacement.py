"""Displacement — an unusually large range candle signaling aggressive
order flow. Used by SMC/ICT to validate that a structure break was driven
by real momentum rather than noise, and to anchor order blocks/FVGs."""
from __future__ import annotations

from core.market_data.models import Candle


def is_displacement_candle(candle: Candle, atr_value: float | None, multiplier: float = 1.5) -> bool:
    if not atr_value or atr_value <= 0:
        return False
    return (candle.high - candle.low) >= atr_value * multiplier
