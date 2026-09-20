"""Session Breakout: an Asian-range breakout traded at London session open.

Grounded in two separate, independently-sourced literatures (see
research/STRATEGY_RESEARCH_REGISTRY.md entries SRR-005/SRR-006):
  - Opening Range Breakout academic studies (Holmberg/Lönnbark/Lundström
    2013; a 2023 5-minute-ORB study) find a real but volatility-dependent
    edge that strengthens once the range and breakout are filtered by
    quality, not traded on a bare break.
  - FX intraday microstructure research (Andersen & Bollerslev 1998;
    Dacorogna et al. 2001) documents the London-New York overlap and the
    London open specifically as the dominant volatility/liquidity window
    in FX — i.e., an "opening range" concept transplanted from equities'
    single daily open maps onto FX as the Asian-session range breaking at
    London's own local open, not the calendar's UTC midnight.

Rules (mechanical, no invented data):
  1. Compute today's Asian-session range (00:00-07:00 UTC, matching
     config/settings.backtest.yaml's session.definitions -- the same
     boundary already used for the Task-37 session breakdown) from the
     entry-timeframe candles.
  2. Trade only within the London session window (07:00-12:00 UTC,
     shortly after the range closes -- required by the ORB literature's
     own finding that the edge decays the later the breakout is traded).
     Ablatable (disabling allows any time after the Asian range closes).
  3. The most recent closed candle must close beyond the Asian high (BUY)
     or Asian low (SELL) -- this sets direction and cannot be ablated,
     like BOS/trend in the other strategies.
  4. That breakout candle should show real momentum (a displacement
     candle), not a marginal poke past the level -- ablatable.

SL sits on the opposite side of the Asian range (ATR-buffered); TP1/TP2
target the nearest opposing liquidity pool, else an ATR-based projection
-- never a fixed R:R, consistent with every other strategy here.

Confidence scoring follows the same independent-component pattern as the
other strategies. This is a brand-new strategy with no legacy arithmetic
to reproduce, so DEFAULT_WEIGHTS starts equal-split across its 4
components; no weight is adopted without the same Train/Validation/OOS/
perturbation pipeline used for Classic/SMC/ICT.
"""
from __future__ import annotations

from datetime import time as dt_time

from core.algorithms.indicators.atr import atr
from core.algorithms.structure.displacement import is_displacement_candle
from core.algorithms.structure.liquidity import find_liquidity_pools
from core.algorithms.structure.swings import find_swing_points
from core.confidence.component_scoring import ComponentWeights, weighted_score
from core.context.analysis_context import AnalysisContext
from core.signals.enums import Direction, StrategyCategory
from core.signals.strategy_signal import PriceZone, StrategySignal
from core.strategies.base import BaseStrategy
from core.strategies.registry import register_strategy

ASIAN_SESSION_START = dt_time(0, 0)
ASIAN_SESSION_END = dt_time(7, 0)
LONDON_WINDOW_START = dt_time(7, 0)
LONDON_WINDOW_END = dt_time(12, 0)
LONDON_WINDOW_MINUTES = 5 * 60

DISPLACEMENT_MULTIPLIER = 1.2
RANGE_QUALITY_ATR_MULTIPLIER = 5.0  # an Asian range this many ATRs wide or more scores 0 on "tightness"
SL_BUFFER_ATR_MULTIPLIER = 0.3
BASE_CONFIDENCE = 55
CONFIDENCE_SCALE = 20

GATE_SESSION_WINDOW = "session_window_gate"
GATE_DISPLACEMENT = "displacement_gate"


@register_strategy
class SessionBreakoutStrategy(BaseStrategy):
    strategy_id = "session_breakout_asian_range"
    category = StrategyCategory.BREAKOUT
    min_lookback_bars = 60

    DEFAULT_WEIGHTS = ComponentWeights({
        "range_quality": 0.25,
        "breakout_strength": 0.25,
        "displacement_strength": 0.25,
        "session_timing": 0.25,
    })

    def __init__(self, weights: ComponentWeights | None = None, disabled_components: frozenset[str] = frozenset()):
        self._weights = weights if weights is not None else self.DEFAULT_WEIGHTS
        self._disabled = disabled_components

    def analyze(self, context: AnalysisContext) -> StrategySignal | None:
        candles = context.entry_timeframe.candles
        if len(candles) < self.min_lookback_bars:
            return None

        as_of_time = context.as_of.time()
        session_window_active = LONDON_WINDOW_START <= as_of_time < LONDON_WINDOW_END
        if GATE_SESSION_WINDOW not in self._disabled:
            if not session_window_active:
                return None
        elif as_of_time < ASIAN_SESSION_END:
            return None  # even disabled, the Asian range must have actually closed

        today = context.as_of.date()
        asian_candles = [c for c in candles if c.timestamp.date() == today and ASIAN_SESSION_START <= c.timestamp.time() < ASIAN_SESSION_END]
        if not asian_candles:
            return None
        asian_high = max(c.high for c in asian_candles)
        asian_low = min(c.low for c in asian_candles)
        if asian_high <= asian_low:
            return None

        atr_values = atr(candles, period=14)
        current_atr = atr_values[-1]
        if not current_atr:
            return None

        breakout_candle = candles[-1]
        if breakout_candle.close > asian_high:
            direction = Direction.BUY
        elif breakout_candle.close < asian_low:
            direction = Direction.SELL
        else:
            return None

        displacement_ok = is_displacement_candle(breakout_candle, current_atr, DISPLACEMENT_MULTIPLIER)
        if GATE_DISPLACEMENT not in self._disabled and not displacement_ok:
            return None

        entry = context.current_price
        sl_buffer = current_atr * SL_BUFFER_ATR_MULTIPLIER
        stop_loss = asian_low - sl_buffer if direction == Direction.BUY else asian_high + sl_buffer
        risk_distance = abs(entry - stop_loss)
        if risk_distance <= 0:
            return None

        swings = find_swing_points(candles, lookback=2)
        pools = find_liquidity_pools(swings, tolerance=current_atr * 0.5) if len(swings) >= 2 else []
        target_pool_kind = "buy_side" if direction == Direction.BUY else "sell_side"
        targets = sorted(
            (p for p in pools if p.kind == target_pool_kind and (p.price > entry if direction == Direction.BUY else p.price < entry)),
            key=lambda p: abs(p.price - entry),
        )
        take_profit_1 = targets[0].price if targets else (entry + risk_distance * 1.5 if direction == Direction.BUY else entry - risk_distance * 1.5)
        take_profit_2 = targets[1].price if len(targets) > 1 else (entry + risk_distance * 3 if direction == Direction.BUY else entry - risk_distance * 3)
        if direction == Direction.BUY and take_profit_2 <= take_profit_1:
            take_profit_2 = take_profit_1 + risk_distance
        if direction == Direction.SELL and take_profit_2 >= take_profit_1:
            take_profit_2 = take_profit_1 - risk_distance

        rationale = [f"Asian range breakout: range [{asian_low:.5f}, {asian_high:.5f}], broke {direction.value.lower()}"]
        if displacement_ok:
            rationale.append("Breakout candle confirmed by displacement")
        rationale.append(f"Traded within London session window ({as_of_time.strftime('%H:%M')} UTC)")

        components = self._score_components(asian_high, asian_low, current_atr, breakout_candle, direction, as_of_time)
        base_confidence = weighted_score(components, self._weights.excluding(self._disabled),
                                          base=BASE_CONFIDENCE, scale=CONFIDENCE_SCALE)

        return StrategySignal(
            strategy_id=self.strategy_id,
            category=self.category,
            direction=direction,
            suggested_entry_zone=PriceZone(entry, entry),
            suggested_stop_loss=stop_loss,
            suggested_take_profit_1=take_profit_1,
            suggested_take_profit_2=take_profit_2,
            rationale=rationale,
            raw_score_components={
                "base_confidence": base_confidence,
                "trend_alignment": True,
                "fvg_confirmation": False,
                "liquidity_confirmation": bool(targets),
            },
            generated_at=context.as_of,
        )

    @staticmethod
    def _score_components(asian_high, asian_low, current_atr, breakout_candle, direction, as_of_time) -> dict[str, float]:
        range_width = asian_high - asian_low
        range_quality = max(0.0, min(1.0 - (range_width / (current_atr * RANGE_QUALITY_ATR_MULTIPLIER)), 1.0))

        if direction == Direction.BUY:
            breakout_strength = max(0.0, min((breakout_candle.close - asian_high) / current_atr, 1.0))
        else:
            breakout_strength = max(0.0, min((asian_low - breakout_candle.close) / current_atr, 1.0))

        displacement_ratio = (breakout_candle.high - breakout_candle.low) / (current_atr * DISPLACEMENT_MULTIPLIER) if current_atr else 0.0
        displacement_strength = max(0.0, min(displacement_ratio - 1.0, 1.0))

        minutes_into_window = (as_of_time.hour * 60 + as_of_time.minute) - (LONDON_WINDOW_START.hour * 60 + LONDON_WINDOW_START.minute)
        session_timing = max(0.0, min(1.0 - (minutes_into_window / LONDON_WINDOW_MINUTES), 1.0))

        return {
            "range_quality": range_quality,
            "breakout_strength": breakout_strength,
            "displacement_strength": displacement_strength,
            "session_timing": session_timing,
        }
