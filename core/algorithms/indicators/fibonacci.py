"""Fibonacci retracement levels, shared by Classic (retracement entries) and
ICT (the Optimal Trade Entry zone, 0.62-0.79)."""
from __future__ import annotations

from core.signals.enums import Direction
from core.signals.strategy_signal import PriceZone

STANDARD_RATIOS = (0.236, 0.382, 0.5, 0.618, 0.705, 0.786, 1.0)
OTE_START, OTE_END = 0.62, 0.79


def fib_levels(swing_high: float, swing_low: float) -> dict[float, float]:
    span = swing_high - swing_low
    return {ratio: swing_high - span * ratio for ratio in STANDARD_RATIOS}


def ote_zone(swing_high: float, swing_low: float, direction: Direction) -> PriceZone:
    """The 62%-79% retracement zone of the most recent impulse leg."""
    span = swing_high - swing_low
    if direction == Direction.BUY:
        # Retracement down into discount from the high of an upward impulse.
        low = swing_high - span * OTE_END
        high = swing_high - span * OTE_START
    else:
        low = swing_low + span * OTE_START
        high = swing_low + span * OTE_END
    return PriceZone(low=low, high=high)
