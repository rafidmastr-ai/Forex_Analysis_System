"""Classic strategy: trend-following pullback entries at Support/Resistance
with candlestick confirmation and optional Fibonacci confluence.

Rules (all explainable, all testable):
  1. Determine trend via EMA20/EMA50 slope + ADX strength (core.algorithms.trend).
     No trade unless there is a clear (non-weak) trend. Trend also sets the
     signal's direction, so it cannot be ablated like the other components
     — there is no "Classic without trend" version of this strategy.
  2. Find Support/Resistance from clustered swing points. By default, no
     trade unless price is currently near the S/R level that agrees with
     the trend (support in an uptrend, resistance in a downtrend) — this
     gate can be disabled for ablation testing (see `disabled_components`).
  3. Require a candlestick reversal/continuation confirmation at that level
     (bullish/bearish engulfing or pin bar) on the last closed candle —
     also an ablatable gate.
  4. Fibonacci retracement of the latest swing leg is an optional confluence
     bonus, never a hard requirement.
  5. SL sits just beyond the S/R level (ATR-buffered), or an ATR-based
     fallback when the S/R gate is disabled and no level is nearby. TP1/TP2
     come from the next opposing S/R levels when available, else an
     ATR-based projection — never a fixed R:R multiple.

Confidence scoring: `analyze()` computes independent 0..1 evidence scores
per component (`_score_components`) instead of the old sequential
`base += 10` mutation, combined via `weighted_score()`
(core.confidence.component_scoring). `DEFAULT_WEIGHTS` reproduces the
original baseline arithmetic exactly (verified by
tests/unit/test_classic_strategy.py) — sr_quality and candlestick_strength
are real, measurable components exposed for the weight-optimization
framework (`optimization/`) but carry zero weight by default, since the
original design never scored them continuously (only gated on them).

Known limitation (documented, not hidden): full geometric chart-pattern
recognition (head & shoulders, triangles, trendline breaks) and a
standalone "Market Structure" component are out of scope for this version
— "chart pattern" confirmation here is limited to candlestick reversal
patterns plus S/R + trend context, so those conceptual components have no
independent score to optimize.
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
from core.confidence.component_scoring import ComponentWeights, weighted_score
from core.context.analysis_context import AnalysisContext
from core.signals.enums import Direction, StrategyCategory
from core.signals.strategy_signal import PriceZone, StrategySignal
from core.strategies.base import BaseStrategy
from core.strategies.registry import register_strategy

PROXIMITY_ATR_MULTIPLIER = 1.0
SL_BUFFER_ATR_MULTIPLIER = 0.5
BASE_CONFIDENCE = 55
CONFIDENCE_SCALE = 15  # matches the old +5 (trend) + +10 (fib) ceiling exactly

# Ablatable gates (structural — remove the trade-generation requirement).
GATE_SUPPORT_RESISTANCE = "support_resistance_gate"
GATE_CANDLESTICK = "candlestick_gate"


@register_strategy
class ClassicStrategy(BaseStrategy):
    strategy_id = "classic_sr_trend_fib"
    category = StrategyCategory.CLASSIC
    min_lookback_bars = 60

    # Fraction of CONFIDENCE_SCALE each component contributes when it scores
    # 1.0. sr_quality/candlestick_strength default to 0 to keep the baseline
    # identical to the pre-refactor implementation.
    DEFAULT_WEIGHTS = ComponentWeights({
        "trend_strength": 1 / 3,
        "fibonacci": 2 / 3,
        "sr_quality": 0.0,
        "candlestick_strength": 0.0,
    })

    def __init__(self, weights: ComponentWeights | None = None, disabled_components: frozenset[str] = frozenset()):
        self._weights = weights if weights is not None else self.DEFAULT_WEIGHTS
        self._disabled = disabled_components

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

        current_price = context.current_price
        nearest = min(relevant_levels, key=lambda lv: abs(lv.price - current_price)) if relevant_levels else None

        sr_gate_active = GATE_SUPPORT_RESISTANCE not in self._disabled
        if sr_gate_active:
            if nearest is None:
                return None
            if abs(nearest.price - current_price) > current_atr * PROXIMITY_ATR_MULTIPLIER:
                return None

        prev, curr = candles[-2], candles[-1]
        if trend.direction == Direction.BUY:
            confirmed = is_bullish_engulfing(prev, curr) or pin_bar_direction(curr) == "bullish"
        else:
            confirmed = is_bearish_engulfing(prev, curr) or pin_bar_direction(curr) == "bearish"
        candlestick_gate_active = GATE_CANDLESTICK not in self._disabled
        if candlestick_gate_active and not confirmed:
            return None

        rationale = [f"Trend alignment: EMA20/EMA50 {trend.direction.value} slope, ADX {trend.strength}"]
        if nearest is not None:
            rationale.append(f"Price at {same_kind} level ~{nearest.price:.5f} ({nearest.touches} touches)")
        if confirmed:
            rationale.append("Candlestick confirmation (engulfing/pin bar)")

        fib_confluence = self._check_fibonacci_confluence(swings, current_price, trend.direction)
        if fib_confluence:
            rationale.append("Fibonacci retracement confluence (38.2%-61.8%)")

        components = self._score_components(trend, nearest, confirmed, fib_confluence)
        base_confidence = weighted_score(components, self._weights.excluding(self._disabled),
                                          base=BASE_CONFIDENCE, scale=CONFIDENCE_SCALE)

        entry = current_price
        sl_buffer = current_atr * SL_BUFFER_ATR_MULTIPLIER
        if nearest is not None:
            stop_loss = (nearest.price - sl_buffer) if trend.direction == Direction.BUY else (nearest.price + sl_buffer)
        else:
            # S/R gate disabled and no level nearby: fall back to a pure ATR stop.
            fallback_distance = current_atr * 2
            stop_loss = entry - fallback_distance if trend.direction == Direction.BUY else entry + fallback_distance
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
    def _score_components(trend, nearest, confirmed: bool, fib_confluence: bool) -> dict[str, float]:
        return {
            "trend_strength": 1.0 if trend.strength == "strong" else 0.0,
            "fibonacci": 1.0 if fib_confluence else 0.0,
            "sr_quality": min(nearest.touches / 3, 1.0) if nearest is not None else 0.0,
            "candlestick_strength": 1.0 if confirmed else 0.0,
        }

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
