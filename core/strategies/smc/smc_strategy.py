"""SMC (Smart Money Concepts) strategy: structure break + order block/FVG
retracement entry, filtered by premium/discount and liquidity sweep.

Rules (all real logic, not just named concepts):
  1. Detect Break of Structure / Change of Character (core.algorithms.structure
     .market_structure) from swing points. The most recent event sets the
     candidate direction — no trade if there is none.
  2. The breaking candle must be a displacement candle (ATR-relative) — a
     structure break on a small candle is not trusted.
  3. Find the Order Block that produced that break. No trade without one.
  4. Price must currently be retracing into that Order Block (or a Fair
     Value Gap formed during the same impulse) — this is the entry trigger,
     not a bare structure break.
  5. Premium/Discount filter: a BUY is only taken from discount/equilibrium,
     a SELL only from premium/equilibrium — rejects chasing price into the
     wrong side of the range.
  6. A liquidity sweep in the entry direction shortly before the break is an
     optional confluence bonus (the classic "stop hunt then reversal").

SL sits just beyond the Order Block; TP1/TP2 target the nearest opposing
liquidity pools when present, else an ATR-based projection.
"""
from __future__ import annotations

from core.algorithms.indicators.atr import atr
from core.algorithms.structure.displacement import is_displacement_candle
from core.algorithms.structure.fair_value_gap import find_fair_value_gaps
from core.algorithms.structure.liquidity import find_liquidity_pools, is_liquidity_sweep
from core.algorithms.structure.market_structure import detect_structure_events
from core.algorithms.structure.order_blocks import find_order_blocks
from core.algorithms.structure.premium_discount import premium_discount_zone
from core.algorithms.structure.swings import find_swing_points
from core.context.analysis_context import AnalysisContext
from core.signals.enums import Direction, StrategyCategory
from core.signals.strategy_signal import PriceZone, StrategySignal
from core.strategies.base import BaseStrategy
from core.strategies.registry import register_strategy

OB_ENTRY_BUFFER_ATR_MULTIPLIER = 0.2
SL_BUFFER_ATR_MULTIPLIER = 0.3
DISPLACEMENT_MULTIPLIER = 1.2


@register_strategy
class SMCStrategy(BaseStrategy):
    strategy_id = "smc_structure_ob_fvg"
    category = StrategyCategory.SMC
    min_lookback_bars = 60

    def analyze(self, context: AnalysisContext) -> StrategySignal | None:
        candles = context.entry_timeframe.candles
        if len(candles) < self.min_lookback_bars:
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

        order_blocks = find_order_blocks(candles, [last_event], lookback=15)
        if not order_blocks:
            return None
        ob = order_blocks[0]

        local_slice = candles[ob.index: min(last_event.index + 2, len(candles))]
        fvgs = [f for f in find_fair_value_gaps(local_slice) if f.direction == direction]
        matching_fvg = fvgs[0] if fvgs else None

        recent_swings = swings[-10:]
        highs = [s.price for s in recent_swings if s.kind == "high"]
        lows = [s.price for s in recent_swings if s.kind == "low"]
        if not highs or not lows:
            return None
        zone = premium_discount_zone(max(highs), min(lows), context.current_price)
        if direction == Direction.BUY and zone == "premium":
            return None
        if direction == Direction.SELL and zone == "discount":
            return None

        buffer = current_atr * OB_ENTRY_BUFFER_ATR_MULTIPLIER
        in_ob = (ob.zone.low - buffer) <= context.current_price <= (ob.zone.high + buffer)
        in_fvg = matching_fvg is not None and matching_fvg.zone.low <= context.current_price <= matching_fvg.zone.high
        if not (in_ob or in_fvg):
            return None

        pools = find_liquidity_pools(swings, tolerance=current_atr * 0.5)
        opposite_pool_kind = "sell_side" if direction == Direction.BUY else "buy_side"
        sweep_confirmed = any(
            is_liquidity_sweep(c, p)
            for c in candles[max(0, last_event.index - 5): last_event.index + 1]
            for p in pools if p.kind == opposite_pool_kind
        )

        entry = context.current_price
        sl_buffer = current_atr * SL_BUFFER_ATR_MULTIPLIER
        stop_loss = ob.zone.low - sl_buffer if direction == Direction.BUY else ob.zone.high + sl_buffer
        risk_distance = abs(entry - stop_loss)
        if risk_distance <= 0:
            return None

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

        rationale = [
            f"{last_event.kind} confirmed by a displacement candle",
            f"Order Block retracement entry ({direction.value})",
            f"Price in {zone} zone",
        ]
        base_confidence = 55
        if matching_fvg is not None:
            rationale.append("Fair Value Gap confluence")
            base_confidence += 10
        if sweep_confirmed:
            rationale.append("Liquidity sweep confirmation")
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
                "liquidity_confirmation": sweep_confirmed,
            },
            generated_at=context.as_of,
        )
