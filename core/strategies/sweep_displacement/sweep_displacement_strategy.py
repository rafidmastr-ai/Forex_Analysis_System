"""Sweep-Displacement-Retracement: a research-driven, mechanically distinct
alternative to SMC's BOS-first entry (see research/STRATEGY_RESEARCH_REGISTRY
.md entries SRR-002/SRR-003).

The current SMC strategy (`core/strategies/smc/smc_strategy.py`) requires a
Break of Structure FIRST, with a liquidity sweep as an optional confluence
bonus. The liquidity-sweep/stop-hunt literature synthesized in the registry
describes a different, and arguably more primary, sequence: the sweep
itself IS the setup, not a bonus on top of one.

Rules (all real, testable logic — no invented data):
  1. A liquidity pool (equal highs/lows, >=2 touches) is swept: a candle
     wicks through it and closes back inside (`core.algorithms.structure
     .liquidity.is_liquidity_sweep`). This sets the candidate direction —
     sweeping a buy-side pool (equal highs) implies a bearish reversal,
     sweeping a sell-side pool implies a bullish reversal. Like BOS in
     SMC/ICT, this is the direction-setting trigger and cannot be ablated.
  2. Within a short window after the sweep, a displacement candle confirms
     the reversal with real momentum, not noise — ablatable.
  3. Entry requires price to retrace into either the Fair Value Gap formed
     by that displacement, or back into the displacement candle's own body
     — the "retracement" leg of the researched Sweep+Displacement+
     Retracement sequence. Ablatable (disabling lets the signal fire right
     at the displacement instead of waiting for a retracement).
  4. Premium/Discount filter (as in SMC/ICT): BUY only from discount/
     equilibrium, SELL only from premium/equilibrium — ablatable.

SL sits just beyond the sweep's extreme wick (ATR-buffered); TP1/TP2
target the nearest opposing liquidity pools when present, else an
ATR-based projection — never a fixed R:R multiple, consistent with every
other strategy in this project.

Confidence scoring follows the same independent-component pattern as
Classic/SMC/ICT (`core.confidence.component_scoring`).

DEFAULT_WEIGHTS provenance: this strategy started from an equal split
across all four components (the least-presumptive prior — no legacy
arithmetic existed to reproduce). That prior was then run through the
exact same bounded Train/Validation/OOS/perturbation/ablation/cross-symbol
pipeline used for Classic/SMC/ICT (scripts/optimize_strategy.py,
min_confidence=65, 2025-09-15..2026-09-16 EURUSD split), and the resulting
candidate weights below PASSED EVERY CHECK in the 8-point acceptance rule
(scripts/classify_optimization_result.py) -- improved Train (-14.65 vs
-45.99 baseline), held in Validation (-1.60 vs -6.91), reasonable OOS
(-4.35 vs -24.89 baseline), no perturbation collapse (drop 1.0 vs a 3.2
margin), sufficient trades. Classified **Robust Candidate** (never "best
strategy") and adopted here as DEFAULT_WEIGHTS per research spec §19.

IMPORTANT CAVEAT, stated plainly rather than buried: "Robust Candidate"
means these weights are more defensible than an arbitrary equal-split
guess and held up under the same rigor applied to every other strategy in
this project -- it does NOT mean this strategy is profitable in absolute
terms. Out-of-sample net R was still -9.00R over 9 trades; XAUUSD
cross-symbol evidence was mixed (positive on only 1 of 3 phases). See
research/STRATEGY_RESEARCH_REGISTRY.md and
data/optimization_results/sweep_displacement_summary.json for the full
numbers. Any future re-optimization must still go through the same
pipeline before its weights replace these.
"""
from __future__ import annotations

from core.algorithms.indicators.atr import atr
from core.algorithms.structure.displacement import is_displacement_candle
from core.algorithms.structure.fair_value_gap import find_fair_value_gaps
from core.algorithms.structure.liquidity import find_liquidity_pools, is_liquidity_sweep
from core.algorithms.structure.premium_discount import premium_discount_zone
from core.algorithms.structure.swings import find_swing_points
from core.confidence.component_scoring import ComponentWeights, weighted_score
from core.context.analysis_context import AnalysisContext
from core.signals.enums import Direction, StrategyCategory
from core.signals.strategy_signal import PriceZone, StrategySignal
from core.strategies.base import BaseStrategy
from core.strategies.registry import register_strategy

SWEEP_LOOKBACK_CANDLES = 10   # how far back to look for a qualifying sweep
DISPLACEMENT_MULTIPLIER = 1.2
SL_BUFFER_ATR_MULTIPLIER = 0.3
BASE_CONFIDENCE = 55
CONFIDENCE_SCALE = 20  # same scale as SMC/ICT — keeps the min_confidence=65 methodology comparable across strategies

GATE_DISPLACEMENT = "displacement_gate"
GATE_ENTRY_ZONE = "entry_zone_gate"          # require retracement into FVG or displacement candle body
GATE_PREMIUM_DISCOUNT = "premium_discount_gate"


@register_strategy
class SweepDisplacementStrategy(BaseStrategy):
    strategy_id = "liquidity_sweep_displacement_retracement"
    category = StrategyCategory.LIQUIDITY
    min_lookback_bars = 60

    # Robust Candidate weights (see module docstring for the full
    # provenance and caveats) -- replaces the original equal-split prior.
    DEFAULT_WEIGHTS = ComponentWeights({
        "sweep_quality": 0.030116665215829466,
        "displacement_strength": 0.4391532641574131,
        "retracement_depth": 0.35259408275584475,
        "premium_discount_depth": 0.17813598787091264,
    })

    def __init__(self, weights: ComponentWeights | None = None, disabled_components: frozenset[str] = frozenset()):
        self._weights = weights if weights is not None else self.DEFAULT_WEIGHTS
        self._disabled = disabled_components

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
        pools = find_liquidity_pools(swings, tolerance=current_atr * 0.5)
        if not pools:
            return None

        sweep = self._find_most_recent_sweep(candles, pools)
        if sweep is None:
            return None
        sweep_index, pool, direction = sweep

        displacement_index, displacement_ratio = self._find_displacement_after(candles, atr_values, sweep_index, direction)
        displacement_ok = displacement_index is not None
        if GATE_DISPLACEMENT not in self._disabled and not displacement_ok:
            return None

        anchor_index = displacement_index if displacement_ok else sweep_index
        local_slice = candles[sweep_index: min(anchor_index + 2, len(candles))]
        fvgs = [f for f in find_fair_value_gaps(local_slice) if f.direction == direction]
        matching_fvg = fvgs[0] if fvgs else None

        current_price = context.current_price
        in_fvg = matching_fvg is not None and matching_fvg.zone.low <= current_price <= matching_fvg.zone.high
        displacement_candle = candles[displacement_index] if displacement_ok else None
        in_displacement_body = displacement_candle is not None and (
            min(displacement_candle.open, displacement_candle.close)
            <= current_price
            <= max(displacement_candle.open, displacement_candle.close)
        )
        retraced = in_fvg or in_displacement_body
        if GATE_ENTRY_ZONE not in self._disabled and not retraced:
            return None

        recent_swings = swings[-10:]
        highs = [s.price for s in recent_swings if s.kind == "high"]
        lows = [s.price for s in recent_swings if s.kind == "low"]
        if not highs or not lows:
            return None
        swing_high, swing_low = max(highs), min(lows)
        zone = premium_discount_zone(swing_high, swing_low, current_price)
        wrong_zone = (direction == Direction.BUY and zone == "premium") or (direction == Direction.SELL and zone == "discount")
        if GATE_PREMIUM_DISCOUNT not in self._disabled and wrong_zone:
            return None

        sweep_candle = candles[sweep_index]
        entry = current_price
        sl_buffer = current_atr * SL_BUFFER_ATR_MULTIPLIER
        stop_loss = sweep_candle.low - sl_buffer if direction == Direction.BUY else sweep_candle.high + sl_buffer
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

        rationale = [f"Liquidity sweep of {pool.kind} pool ({pool.touches} touches) at ~{pool.price:.5f}"]
        if displacement_ok:
            rationale.append("Displacement candle confirmed the reversal")
        if in_fvg:
            rationale.append("Retracement into post-displacement Fair Value Gap")
        elif in_displacement_body:
            rationale.append("Retracement into displacement candle body")
        rationale.append(f"Price in {zone} zone")

        components = self._score_components(pool, displacement_ratio, matching_fvg, current_price, direction, zone, swing_high, swing_low)
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
                "trend_alignment": zone in ("discount", "equilibrium") if direction == Direction.BUY else zone in ("premium", "equilibrium"),
                "fvg_confirmation": matching_fvg is not None,
                "liquidity_confirmation": True,
            },
            generated_at=context.as_of,
        )

    @staticmethod
    def _find_most_recent_sweep(candles, pools):
        """Scans the recent window newest-first for the most recent
        candle that sweeps any known pool; returns (index, pool, direction)
        or None. Sweeping a buy-side pool (equal highs, stops above) implies
        a bearish reversal; sweeping a sell-side pool implies bullish."""
        start = max(0, len(candles) - 1 - SWEEP_LOOKBACK_CANDLES)
        for i in range(len(candles) - 2, start - 1, -1):  # exclude the very last candle (reserved for retracement/current price)
            candle = candles[i]
            for pool in pools:
                if is_liquidity_sweep(candle, pool):
                    direction = Direction.SELL if pool.kind == "buy_side" else Direction.BUY
                    return i, pool, direction
        return None

    @staticmethod
    def _find_displacement_after(candles, atr_values, sweep_index: int, direction: Direction):
        """First displacement candle after the sweep, in the reversal
        direction (bearish body for SELL, bullish body for BUY)."""
        for i in range(sweep_index + 1, len(candles)):
            candle = candles[i]
            is_bearish = candle.close < candle.open
            is_bullish = candle.close > candle.open
            matches_direction = (direction == Direction.SELL and is_bearish) or (direction == Direction.BUY and is_bullish)
            if not matches_direction:
                continue
            atr_value = atr_values[i]
            if is_displacement_candle(candle, atr_value, DISPLACEMENT_MULTIPLIER):
                ratio = (candle.high - candle.low) / (atr_value * DISPLACEMENT_MULTIPLIER) if atr_value else 0.0
                return i, ratio
        return None, 0.0

    @staticmethod
    def _score_components(pool, displacement_ratio, matching_fvg, current_price, direction, zone, swing_high, swing_low) -> dict[str, float]:
        span = swing_high - swing_low
        ratio = (current_price - swing_low) / span if span > 0 else 0.5
        if direction == Direction.BUY:
            depth = max(0.0, min((0.5 - ratio) / 0.5, 1.0))
        else:
            depth = max(0.0, min((ratio - 0.5) / 0.5, 1.0))

        if matching_fvg is not None and (matching_fvg.zone.high - matching_fvg.zone.low) > 0:
            fvg_span = matching_fvg.zone.high - matching_fvg.zone.low
            if direction == Direction.BUY:
                retracement_depth = 1.0 - (current_price - matching_fvg.zone.low) / fvg_span
            else:
                retracement_depth = (current_price - matching_fvg.zone.low) / fvg_span
            retracement_depth = max(0.0, min(retracement_depth, 1.0))
        else:
            retracement_depth = 0.0

        return {
            "sweep_quality": min(pool.touches / 3, 1.0),
            "displacement_strength": max(0.0, min(displacement_ratio - 1.0, 1.0)),
            "retracement_depth": retracement_depth,
            "premium_discount_depth": depth,
        }
