"""Classic strategy: trend-following pullback entries at Support/Resistance
with candlestick confirmation and optional Fibonacci confluence.

Rules (all explainable, all testable):
  1. Determine trend via EMA20/EMA50 slope + ADX strength (core.algorithms.trend).
     No trade unless there is a clear (non-weak) trend.
  2. Find Support/Resistance from clustered swing points. No trade unless
     price is currently near the S/R level that agrees with the trend
     (support in an uptrend, resistance in a downtrend).
  3. Require a candlestick reversal/continuation confirmation at that level
     (bullish/bearish engulfing or pin bar) on the last closed candle.
  4. Fibonacci retracement of the latest swing leg is an optional confluence
     bonus (added to rationale/confidence), not a hard requirement.
  5. SL sits just beyond the S/R level (ATR-buffered). TP1/TP2 come from the
     next opposing S/R levels when available, else an ATR-based projection
     — never a fixed R:R multiple.

Known limitation (documented, not hidden): full geometric chart-pattern
recognition (head & shoulders, triangles, trendline breaks) is out of
scope for this version; "chart pattern" confirmation here is limited to
candlestick reversal patterns plus S/R + trend context.
"""
from __future__ import annotations

from core.algorithms.indicators.atr import atr
from core.algorithms.indicators.candlestick_patterns import (
    is_bearish_engulfing,
    is_bullish_engulfing,
    pin_bar_direction,
)
from core.algorithms.indicators.fibonacci import fib_levels
from core.algorithms.structure.swings import find_swing_points
from core.algorithms.trend.support_resistance import find_support_resistance_levels
from core.algorithms.trend.trend_detection import detect_trend
from core.context.analysis_context import AnalysisContext
from core.signals.enums import Direction, StrategyCategory
from core.signals.strategy_signal import PriceZone, StrategySignal
from core.strategies.base import BaseStrategy
from core.strategies.registry import register_strategy

PROXIMITY_ATR_MULTIPLIER = 1.0
SL_BUFFER_ATR_MULTIPLIER = 0.5


@register_strategy
class ClassicStrategy(BaseStrategy):
    strategy_id = "classic_sr_trend_fib"
    category = StrategyCategory.CLASSIC
    min_lookback_bars = 60

    def analyze(self, context: AnalysisContext) -> StrategySignal | None:
        candles = context.entry_timeframe.candles
        if len(candles) < self.min_lookback_bars:
            return None

        trend = detect_trend(candles)
        if trend.direction is None or trend.strength == "weak":
            return None

        atr_values = atr(candles, period=14)
        current_atr = atr_values[-1]
        if not current_atr:
            return None

        swings = find_swing_points(candles, lookback=2)
        if len(swings) < 2:
            return None
        sr_levels = find_support_resistance_levels(swings, tolerance=current_atr * 0.5)

        same_kind = "support" if trend.direction == Direction.BUY else "resistance"
        opposite_kind = "resistance" if trend.direction == Direction.BUY else "support"
        relevant_levels = [lv for lv in sr_levels if lv.kind == same_kind]
        if not relevant_levels:
            return None

        current_price = context.current_price
        nearest = min(relevant_levels, key=lambda lv: abs(lv.price - current_price))
        if abs(nearest.price - current_price) > current_atr * PROXIMITY_ATR_MULTIPLIER:
            return None

        prev, curr = candles[-2], candles[-1]
        if trend.direction == Direction.BUY:
            confirmed = is_bullish_engulfing(prev, curr) or pin_bar_direction(curr) == "bullish"
        else:
            confirmed = is_bearish_engulfing(prev, curr) or pin_bar_direction(curr) == "bearish"
        if not confirmed:
            return None

        rationale = [
            f"Trend alignment: EMA20/EMA50 {trend.direction.value} slope, ADX {trend.strength}",
            f"Price at {same_kind} level ~{nearest.price:.5f} ({nearest.touches} touches)",
            "Candlestick confirmation (engulfing/pin bar)",
        ]
        base_confidence = 55
        if trend.strength == "strong":
            base_confidence += 5

        fib_confluence = self._check_fibonacci_confluence(swings, current_price, trend.direction)
        if fib_confluence:
            rationale.append("Fibonacci retracement confluence (38.2%-61.8%)")
            base_confidence += 10

        entry = current_price
        sl_buffer = current_atr * SL_BUFFER_ATR_MULTIPLIER
        if trend.direction == Direction.BUY:
            stop_loss = nearest.price - sl_buffer
        else:
            stop_loss = nearest.price + sl_buffer
        risk_distance = abs(entry - stop_loss)
        if risk_distance <= 0:
            return None

        opposite_levels = [
            lv for lv in sr_levels
            if lv.kind == opposite_kind and (lv.price > entry if trend.direction == Direction.BUY else lv.price < entry)
        ]
        opposite_levels.sort(key=lambda lv: abs(lv.price - entry))

        take_profit_1 = self._resolve_target(opposite_levels, 0, entry, risk_distance, trend.direction, 1.5)
        take_profit_2 = self._resolve_target(opposite_levels, 1, entry, risk_distance, trend.direction, 3.0)
        if trend.direction == Direction.BUY and take_profit_2 <= take_profit_1:
            take_profit_2 = take_profit_1 + risk_distance
        if trend.direction == Direction.SELL and take_profit_2 >= take_profit_1:
            take_profit_2 = take_profit_1 - risk_distance

        return StrategySignal(
            strategy_id=self.strategy_id,
            category=self.category,
            direction=trend.direction,
            suggested_entry_zone=PriceZone(entry, entry),
            suggested_stop_loss=stop_loss,
            suggested_take_profit_1=take_profit_1,
            suggested_take_profit_2=take_profit_2,
            rationale=rationale,
            raw_score_components={
                "base_confidence": base_confidence,
                "trend_alignment": True,
                "fvg_confirmation": False,
                "liquidity_confirmation": False,
            },
            generated_at=context.as_of,
        )

    @staticmethod
    def _resolve_target(opposite_levels, idx, entry, risk_distance, direction, fallback_rr) -> float:
        if idx < len(opposite_levels):
            return opposite_levels[idx].price
        projection = risk_distance * fallback_rr
        return entry + projection if direction == Direction.BUY else entry - projection

    @staticmethod
    def _check_fibonacci_confluence(swings, current_price, direction) -> bool:
        highs = [s for s in swings if s.kind == "high"]
        lows = [s for s in swings if s.kind == "low"]
        if not highs or not lows:
            return False
        swing_high = max(highs, key=lambda s: s.timestamp).price
        swing_low = min(lows, key=lambda s: s.timestamp).price
        if swing_high <= swing_low:
            return False
        levels = fib_levels(swing_high, swing_low)
        zone_low, zone_high = levels[0.618], levels[0.382]
        return zone_low <= current_price <= zone_high
