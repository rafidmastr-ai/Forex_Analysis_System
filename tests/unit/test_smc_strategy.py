"""SMC strategy tests.

The underlying algorithms (swing detection, BOS/CHoCH, order blocks, FVG,
liquidity, premium/discount) are already unit-tested in test_algorithms.py.
Here we monkeypatch them to fixed, deterministic fixtures so we can test
SMCStrategy's own decision logic (which signals to combine, which filters
gate a trade, how confidence/rationale are built) in isolation — hand
-crafting raw candle data that reliably produces a specific fractal/BOS
pattern is inherently fragile (small changes shift swing detection), so
this is the more reliable way to pin down the strategy's branching.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import core.strategies.smc.smc_strategy as smc_module
from core.algorithms.structure.liquidity import LiquidityPool
from core.algorithms.structure.market_structure import StructureEvent
from core.algorithms.structure.order_blocks import OrderBlock
from core.algorithms.structure.swings import SwingPoint
from core.context.analysis_context import AnalysisContext
from core.market_data.models import Candle, CandleSeries, Symbol, Timeframe
from core.signals.enums import Direction
from core.signals.strategy_signal import PriceZone
from core.strategies.smc.smc_strategy import SMCStrategy

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
SYMBOL = Symbol(name="EURUSD", pip_size=0.0001, digits=5, contract_size=100000)


def _dummy_candles(n: int = 60) -> list[Candle]:
    return [Candle(timestamp=BASE + timedelta(minutes=i), open=1.1, high=1.1005, low=1.0995, close=1.1, volume=100)
            for i in range(n)]


def _context(current_price: float, candles: list[Candle]) -> AnalysisContext:
    series = CandleSeries(symbol=SYMBOL, timeframe=Timeframe.M15, candles=candles)
    return AnalysisContext(
        symbol=SYMBOL, current_bid=current_price, current_ask=current_price, session="London",
        higher_timeframe=series, middle_timeframe=series, entry_timeframe=series, as_of=candles[-1].timestamp,
    )


def _patch_common(monkeypatch, *, direction=Direction.BUY, zone="discount", displacement=True,
                   order_blocks=None, fvgs=None, pools=None, sweep=False, events=None):
    swings = [
        SwingPoint(index=10, timestamp=BASE, price=1.1050, kind="high"),
        SwingPoint(index=20, timestamp=BASE, price=1.0950, kind="low"),
    ]
    default_event = StructureEvent(kind="CHoCH", direction=direction, timestamp=BASE, price=1.1, broken_level=1.1050, index=45)

    monkeypatch.setattr(smc_module, "atr", lambda candles, period=14: [0.0010] * len(candles))
    monkeypatch.setattr(smc_module, "find_swing_points", lambda candles, lookback=2: swings)
    monkeypatch.setattr(smc_module, "detect_structure_events", lambda candles, s: events if events is not None else [default_event])
    monkeypatch.setattr(smc_module, "is_displacement_candle", lambda candle, atr_value, mult: displacement)
    monkeypatch.setattr(smc_module, "find_order_blocks", lambda candles, ev, lookback=15: (
        order_blocks if order_blocks is not None else [
            OrderBlock(direction=direction, zone=PriceZone(1.0990, 1.1000), timestamp=BASE, index=40, structure_event_index=45)
        ]
    ))
    monkeypatch.setattr(smc_module, "find_fair_value_gaps", lambda candles: fvgs if fvgs is not None else [])
    monkeypatch.setattr(smc_module, "premium_discount_zone", lambda high, low, price: zone)
    monkeypatch.setattr(smc_module, "find_liquidity_pools", lambda swings, tolerance, min_touches=2: pools if pools is not None else [])
    monkeypatch.setattr(smc_module, "is_liquidity_sweep", lambda candle, pool: sweep)


def test_smc_produces_buy_signal_from_order_block_retracement(monkeypatch):
    _patch_common(monkeypatch)
    candles = _dummy_candles()
    ctx = _context(current_price=1.0995, candles=candles)  # inside OB zone [1.0990, 1.1000]

    signal = SMCStrategy().analyze(ctx)

    assert signal is not None
    assert signal.direction == Direction.BUY
    assert signal.raw_score_components["base_confidence"] == 55
    assert signal.raw_score_components["fvg_confirmation"] is False
    assert any("Order Block" in r for r in signal.rationale)


def test_smc_adds_confidence_for_fvg_confluence(monkeypatch):
    from core.algorithms.structure.fair_value_gap import FVGZone
    fvg = FVGZone(direction=Direction.BUY, zone=PriceZone(1.0990, 1.1000), index=42, timestamp=BASE)
    _patch_common(monkeypatch, fvgs=[fvg])
    ctx = _context(current_price=1.0995, candles=_dummy_candles())

    signal = SMCStrategy().analyze(ctx)

    assert signal is not None
    assert signal.raw_score_components["fvg_confirmation"] is True
    assert signal.raw_score_components["base_confidence"] == 65
    assert any("Fair Value Gap" in r for r in signal.rationale)


def test_smc_adds_confidence_for_liquidity_sweep(monkeypatch):
    pool = LiquidityPool(kind="sell_side", price=1.0940, touches=2)
    _patch_common(monkeypatch, pools=[pool], sweep=True)
    ctx = _context(current_price=1.0995, candles=_dummy_candles())

    signal = SMCStrategy().analyze(ctx)

    assert signal is not None
    assert signal.raw_score_components["liquidity_confirmation"] is True
    assert signal.raw_score_components["base_confidence"] == 65


def test_smc_rejects_buy_from_premium_zone(monkeypatch):
    _patch_common(monkeypatch, zone="premium")
    ctx = _context(current_price=1.0995, candles=_dummy_candles())

    assert SMCStrategy().analyze(ctx) is None


def test_smc_rejects_non_displacement_break(monkeypatch):
    _patch_common(monkeypatch, displacement=False)
    ctx = _context(current_price=1.0995, candles=_dummy_candles())

    assert SMCStrategy().analyze(ctx) is None


def test_smc_no_structure_events_returns_none(monkeypatch):
    _patch_common(monkeypatch, events=[])
    ctx = _context(current_price=1.0995, candles=_dummy_candles())

    assert SMCStrategy().analyze(ctx) is None


def test_smc_no_order_block_returns_none(monkeypatch):
    _patch_common(monkeypatch, order_blocks=[])
    ctx = _context(current_price=1.0995, candles=_dummy_candles())

    assert SMCStrategy().analyze(ctx) is None


def test_smc_price_far_from_ob_and_fvg_returns_none(monkeypatch):
    _patch_common(monkeypatch)
    ctx = _context(current_price=1.5000, candles=_dummy_candles())  # nowhere near the OB zone

    assert SMCStrategy().analyze(ctx) is None


def test_smc_insufficient_lookback_returns_none(monkeypatch):
    _patch_common(monkeypatch)
    ctx = _context(current_price=1.0995, candles=_dummy_candles(n=10))

    assert SMCStrategy().analyze(ctx) is None


def test_smc_strategy_is_registered():
    from core.strategies.registry import registry
    import core.strategies.smc  # noqa: F401

    ids = [m.strategy_id for m in registry.all()]
    assert "smc_structure_ob_fvg" in ids
