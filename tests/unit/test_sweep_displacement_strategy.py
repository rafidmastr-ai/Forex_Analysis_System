"""SweepDisplacementStrategy tests.

Same approach as test_smc_strategy.py: the underlying algorithms are
already unit-tested elsewhere, so here we monkeypatch them to fixed,
deterministic fixtures to test the strategy's own branching (which gates
apply, how direction is set by which pool kind was swept, how weights
change the resulting confidence).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import core.strategies.sweep_displacement.sweep_displacement_strategy as sd_module
from core.algorithms.structure.fair_value_gap import FVGZone
from core.algorithms.structure.liquidity import LiquidityPool
from core.algorithms.structure.swings import SwingPoint
from core.confidence.component_scoring import ComponentWeights
from core.context.analysis_context import AnalysisContext
from core.market_data.models import Candle, CandleSeries, Symbol, Timeframe
from core.signals.enums import Direction
from core.signals.strategy_signal import PriceZone
from core.strategies.sweep_displacement.sweep_displacement_strategy import (
    GATE_DISPLACEMENT,
    SweepDisplacementStrategy,
)

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
SYMBOL = Symbol(name="EURUSD", pip_size=0.0001, digits=5, contract_size=100000)


def _candles(n: int = 60) -> list[Candle]:
    out = []
    for i in range(n):
        # candle -5 (relative to the end) is the "sweep" candle, -3 the "displacement" candle
        if i == n - 5:
            out.append(Candle(timestamp=BASE + timedelta(minutes=i), open=1.1050, high=1.1080, low=1.1040, close=1.1045, volume=100))
        elif i == n - 3:
            out.append(Candle(timestamp=BASE + timedelta(minutes=i), open=1.1040, high=1.1042, low=1.0990, close=1.0995, volume=100))
        else:
            out.append(Candle(timestamp=BASE + timedelta(minutes=i), open=1.1, high=1.1005, low=1.0995, close=1.1, volume=100))
    return out


def _context(current_price: float, candles: list[Candle]) -> AnalysisContext:
    series = CandleSeries(symbol=SYMBOL, timeframe=Timeframe.M15, candles=candles)
    return AnalysisContext(
        symbol=SYMBOL, current_bid=current_price, current_ask=current_price, session="London",
        higher_timeframe=series, middle_timeframe=series, entry_timeframe=series, as_of=candles[-1].timestamp,
    )


def _patch_common(monkeypatch, *, pool_kind="buy_side", displacement=True, fvg_direction=None,
                   in_fvg=True, zone="discount"):
    # Content isn't inspected directly (find_liquidity_pools/premium_discount_zone are patched below),
    # but the strategy requires >=2 swings with at least one "high" and one "low" before proceeding.
    swings = [
        SwingPoint(index=10, timestamp=BASE, price=1.1050, kind="high"),
        SwingPoint(index=20, timestamp=BASE, price=1.0950, kind="low"),
    ]
    pool = LiquidityPool(kind=pool_kind, price=1.1050, touches=3)
    expected_direction = Direction.SELL if pool_kind == "buy_side" else Direction.BUY
    fvg_dir = fvg_direction if fvg_direction is not None else expected_direction

    monkeypatch.setattr(sd_module, "atr", lambda candles, period=14: [0.0010] * len(candles))
    monkeypatch.setattr(sd_module, "find_swing_points", lambda candles, lookback=2: swings)
    monkeypatch.setattr(sd_module, "find_liquidity_pools", lambda swings, tolerance: [pool])
    monkeypatch.setattr(sd_module, "is_liquidity_sweep", lambda candle, p: (candle.high == 1.1080 or candle.low == 1.1040) if p is pool else False)
    # Real bearish/bullish body detection inside _find_displacement_after only ever matches a SELL-shaped
    # fixture candle, so directly patch the method to control displacement-found/not-found deterministically
    # regardless of which direction (BUY/SELL) this test is exercising.
    monkeypatch.setattr(
        sd_module.SweepDisplacementStrategy, "_find_displacement_after",
        staticmethod(lambda candles, atr_values, sweep_index, direction: (sweep_index + 2, 2.0) if displacement else (None, 0.0)),
    )
    fvg = FVGZone(direction=fvg_dir, zone=PriceZone(1.0980, 1.1000), index=0, timestamp=BASE)
    monkeypatch.setattr(sd_module, "find_fair_value_gaps", lambda candles: [fvg])
    monkeypatch.setattr(sd_module, "premium_discount_zone", lambda hi, lo, price: zone)
    return pool, expected_direction


def test_default_weights_are_the_robust_candidate_from_optimization():
    """Regression pin: DEFAULT_WEIGHTS was updated from an equal-split
    prior to the Robust Candidate found by scripts/optimize_strategy.py
    (see the module docstring for full provenance/caveats). Any future
    re-optimization must go through that same pipeline before changing
    this value -- this test just catches an accidental/silent edit."""
    weights = sd_module.SweepDisplacementStrategy.DEFAULT_WEIGHTS.weights
    assert weights == {
        "sweep_quality": 0.030116665215829466,
        "displacement_strength": 0.4391532641574131,
        "retracement_depth": 0.35259408275584475,
        "premium_discount_depth": 0.17813598787091264,
    }


def test_no_trade_when_no_sweep_found(monkeypatch):
    swings = [
        SwingPoint(index=10, timestamp=BASE, price=1.1050, kind="high"),
        SwingPoint(index=20, timestamp=BASE, price=1.0950, kind="low"),
    ]
    monkeypatch.setattr(sd_module, "atr", lambda candles, period=14: [0.0010] * len(candles))
    monkeypatch.setattr(sd_module, "find_swing_points", lambda candles, lookback=2: swings)
    monkeypatch.setattr(sd_module, "find_liquidity_pools", lambda swings, tolerance: [LiquidityPool(kind="buy_side", price=1.1050, touches=3)])
    monkeypatch.setattr(sd_module, "is_liquidity_sweep", lambda candle, pool: False)

    strategy = SweepDisplacementStrategy()
    result = strategy.analyze(_context(1.0995, _candles()))

    assert result is None


def test_sweeping_buy_side_pool_produces_sell_signal(monkeypatch):
    candles = _candles()
    _patch_common(monkeypatch, pool_kind="buy_side", zone="premium")

    strategy = SweepDisplacementStrategy()
    result = strategy.analyze(_context(1.0995, candles))

    assert result is not None
    assert result.direction == Direction.SELL
    assert result.suggested_stop_loss > result.suggested_entry_zone.high  # SL beyond the swept high


def test_sweeping_sell_side_pool_produces_buy_signal(monkeypatch):
    candles = _candles()
    _patch_common(monkeypatch, pool_kind="sell_side", zone="discount")

    strategy = SweepDisplacementStrategy()
    result = strategy.analyze(_context(1.0995, candles))

    assert result is not None
    assert result.direction == Direction.BUY


def test_displacement_gate_blocks_trade_when_disabled_component_not_set(monkeypatch):
    candles = _candles()
    _patch_common(monkeypatch, pool_kind="buy_side", displacement=False, zone="premium")

    strategy = SweepDisplacementStrategy()
    result = strategy.analyze(_context(1.0995, candles))

    assert result is None


def test_displacement_gate_can_be_disabled_for_ablation(monkeypatch):
    candles = _candles()
    _patch_common(monkeypatch, pool_kind="buy_side", displacement=False, zone="premium")

    strategy = SweepDisplacementStrategy(disabled_components=frozenset({GATE_DISPLACEMENT, "entry_zone_gate"}))
    result = strategy.analyze(_context(1.0995, candles))

    assert result is not None


def test_entry_zone_gate_requires_retracement(monkeypatch):
    candles = _candles()
    # FVG direction mismatches so in_fvg is False, and current price is outside the displacement candle body too
    _patch_common(monkeypatch, pool_kind="buy_side", zone="premium", fvg_direction=Direction.BUY)

    strategy = SweepDisplacementStrategy()
    result = strategy.analyze(_context(1.2000, candles))  # far outside any zone

    assert result is None


def test_custom_weights_change_confidence_score(monkeypatch):
    candles = _candles()
    _patch_common(monkeypatch, pool_kind="buy_side", zone="premium")

    default_result = SweepDisplacementStrategy().analyze(_context(1.0995, candles))
    weighted_result = SweepDisplacementStrategy(
        weights=ComponentWeights({"sweep_quality": 1.0, "displacement_strength": 0.0, "retracement_depth": 0.0, "premium_discount_depth": 0.0})
    ).analyze(_context(1.0995, candles))

    assert default_result is not None and weighted_result is not None
    # sweep_quality=touches/3=1.0 dominates fully under the all-weight-on-sweep config -> should hit the confidence ceiling
    assert weighted_result.raw_score_components["base_confidence"] == sd_module.BASE_CONFIDENCE + sd_module.CONFIDENCE_SCALE
