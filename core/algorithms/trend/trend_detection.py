"""Trend detection shared by Classic/SMC/ICT: EMA slope for direction, ADX
for strength. Independent of any strategy."""
from __future__ import annotations

from dataclasses import dataclass

from core.algorithms.indicators.adx import adx
from core.algorithms.indicators.moving_average import ema
from core.market_data.models import Candle
from core.signals.enums import Direction


@dataclass(frozen=True)
class TrendResult:
    direction: Direction | None  # None means no clear trend (ranging)
    strength: str  # "weak" | "moderate" | "strong"
    adx_value: float | None


def detect_trend(candles: list[Candle], fast_period: int = 20, slow_period: int = 50, adx_period: int = 14) -> TrendResult:
    if len(candles) < max(slow_period, adx_period * 2) + 1:
        return TrendResult(direction=None, strength="weak", adx_value=None)

    fast = ema(candles, fast_period)
    slow = ema(candles, slow_period)
    adx_values = adx(candles, adx_period)

    last_fast, last_slow, last_adx = fast[-1], slow[-1], adx_values[-1]
    if last_fast is None or last_slow is None:
        return TrendResult(direction=None, strength="weak", adx_value=last_adx)

    if last_fast > last_slow:
        direction = Direction.BUY
    elif last_fast < last_slow:
        direction = Direction.SELL
    else:
        direction = None

    if last_adx is None:
        strength = "weak"
    elif last_adx >= 25:
        strength = "strong"
    elif last_adx >= 15:
        strength = "moderate"
    else:
        strength = "weak"

    return TrendResult(direction=direction, strength=strength, adx_value=last_adx)
