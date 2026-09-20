"""ICT strategy: kill-zone-gated structure break with an Optimal Trade
Entry (OTE) or Fair Value Gap retracement trigger.

Rules:
  1. No trade outside an active ICT Kill Zone (New York-time windows,
     DST-aware via zoneinfo — never the server/user's own timezone).
  2. Detect Break of Structure / Change of Character, confirmed by a
     displacement candle (same primitives as SMC).
  3. Build the OTE zone (62%-79% retracement) of the impulse leg that
     produced the break. Entry requires price inside that zone, or inside
     a Fair Value Gap formed during the same impulse.
  4. Premium/Discount filter: BUY only from discount/equilibrium, SELL
     only from premium/equilibrium.
  5. Breaker Block alignment is an optional confidence bonus, not a
     requirement.

SL sits beyond the impulse's origin swing point; TP1/TP2 target the
nearest opposing liquidity pools, else an ATR-based projection.
"""
from __future__ import annotations

from core.algorithms.indicators.atr import atr
from core.algorithms.indicators.fibonacci import ote_zone
from core.algorithms.session.kill_zones import active_kill_zone
from core.algorithms.structure.breaker_blocks import find_breaker_blocks
from core.algorithms.structure.displacement import is_displacement_candle
from core.algorithms.structure.fair_value_gap import find_fair_value_gaps
from core.algorithms.structure.liquidity import find_liquidity_pools
from core.algorithms.structure.market_structure import detect_structure_events
from core.algorithms.structure.order_blocks import find_order_blocks
from core.algorithms.structure.premium_discount import premium_discount_zone
from core.algorithms.structure.swings import find_swing_points
from core.context.analysis_context import AnalysisContext
from core.signals.enums import Direction, StrategyCategory
from core.signals.strategy_signal import PriceZone, StrategySignal
from core.strategies.base import BaseStrategy
from core.strategies.registry import register_strategy

SL_BUFFER_ATR_MULTIPLIER = 0.3
DISPLACEMENT_MULTIPLIER = 1.2


@register_strategy
class ICTStrategy(BaseStrategy):
    strategy_id = "ict_ote_killzone"
    category = StrategyCategory.ICT
    min_lookback_bars = 60

    def analyze(self, context: AnalysisContext) -> StrategySignal | None:
        candles = context.entry_timeframe.candles
        if len(candles) < self.min_lookback_bars:
            return None

        kill_zone = active_kill_zone(context.as_of)
        if kill_zone is None:
            return None

        atr_values = atr(candles, period=14)
        current_atr = atr_values[-1]
        if not current_atr:
            return None

        swings = find_swing_points(candles, lookback=2)
        if len(swings) < 2:
            return None
        events = detect_structure_events(candles, swings)
        if not events:
            return None

        last_event = events[-1]
        direction = last_event.direction
        break_candle = candles[last_event.index]
        if not is_displacement_candle(break_candle, current_atr, DISPLACEMENT_MULTIPLIER):
            return None

        impulse_start = self._find_impulse_start(swings, last_event.index, direction)
        if impulse_start is None:
            return None
        if direction == Direction.BUY:
            swing_low, swing_high = impulse_start.price, last_event.price
        else:
            swing_high, swing_low = impulse_start.price, last_event.price
        if swing_high <= swing_low:
            return None

        zone_ote = ote_zone(swing_high, swing_low, direction)
        local_slice = candles[impulse_start.index: min(last_event.index + 2, len(candles))]
        fvgs = [f for f in find_fair_value_gaps(local_slice) if f.direction == direction]
        matching_fvg = fvgs[0] if fvgs else None

        current_price = context.current_price
        in_ote = zone_ote.low <= current_price <= zone_ote.high
        in_fvg = matching_fvg is not None and matching_fvg.zone.low <= current_price <= matching_fvg.zone.high
        if not (in_ote or in_fvg):
            return None

        recent_swings = swings[-10:]
        highs = [s.price for s in recent_swings if s.kind == "high"]
        lows = [s.price for s in recent_swings if s.kind == "low"]
        if not highs or not lows:
            return None
        zone = premium_discount_zone(max(highs), min(lows), current_price)
        if direction == Direction.BUY and zone == "premium":
            return None
        if direction == Direction.SELL and zone == "discount":
            return None

        order_blocks = find_order_blocks(candles, events, lookback=15)
        breakers = find_breaker_blocks(candles, order_blocks)
        breaker_confluence = any(
            b.direction == direction and b.zone.low <= current_price <= b.zone.high for b in breakers
        )

        entry = current_price
        sl_buffer = current_atr * SL_BUFFER_ATR_MULTIPLIER
        stop_loss = swing_low - sl_buffer if direction == Direction.BUY else swing_high + sl_buffer
        risk_distance = abs(entry - stop_loss)
        if risk_distance <= 0:
            return None

        pools = find_liquidity_pools(swings, tolerance=current_atr * 0.5)
        target_kind = "buy_side" if direction == Direction.BUY else "sell_side"
        targets = sorted(
            (p for p in pools if p.kind == target_kind and (p.price > entry if direction == Direction.BUY else p.price < entry)),
            key=lambda p: abs(p.price - entry),
        )
        take_profit_1 = targets[0].price if targets else (entry + risk_distance * 1.5 if direction == Direction.BUY else entry - risk_distance * 1.5)
        take_profit_2 = targets[1].price if len(targets) > 1 else (entry + risk_distance * 3 if direction == Direction.BUY else entry - risk_distance * 3)
        if direction == Direction.BUY and take_profit_2 <= take_profit_1:
            take_profit_2 = take_profit_1 + risk_distance
        if direction == Direction.SELL and take_profit_2 >= take_profit_1:
            take_profit_2 = take_profit_1 - risk_distance

        rationale = [
            f"{kill_zone} kill zone active",
            f"{last_event.kind} confirmed by a displacement candle",
            "Price in OTE (62%-79%) retracement zone" if in_ote else "Price in Fair Value Gap",
            f"Price in {zone} zone",
        ]
        base_confidence = 55
        if matching_fvg is not None:
            rationale.append("Fair Value Gap confluence")
            base_confidence += 10
        if breaker_confluence:
            rationale.append("Breaker Block confluence")
            base_confidence += 10

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
                "trend_alignment": zone in ("discount", "equilibrium") if direction == Direction.BUY else zone in ("premium", "equilibrium"),
                "fvg_confirmation": matching_fvg is not None,
                "liquidity_confirmation": breaker_confluence,
            },
            generated_at=context.as_of,
        )

    @staticmethod
    def _find_impulse_start(swings, event_index: int, direction: Direction):
        kind = "low" if direction == Direction.BUY else "high"
        candidates = [s for s in swings if s.kind == kind and s.index < event_index]
        if not candidates:
            return None
        return max(candidates, key=lambda s: s.index)
