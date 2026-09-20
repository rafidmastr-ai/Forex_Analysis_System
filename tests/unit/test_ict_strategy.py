"""ICT strategy tests — same monkeypatching approach as test_smc_strategy.py
for the same reason: the underlying structure/OTE/kill-zone algorithms are
already unit-tested individually; here we pin ICTStrategy's own branching
logic deterministically.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import core.strategies.ict.ict_strategy as ict_module
from core.algorithms.structure.breaker_blocks import BreakerBlock
from core.algorithms.structure.market_structure import StructureEvent
from core.algorithms.structure.swings import SwingPoint
from core.context.analysis_context import AnalysisContext
from core.market_data.models import Candle, CandleSeries, Symbol, Timeframe
from core.signals.enums import Direction
from core.signals.strategy_signal import PriceZone
from core.strategies.ict.ict_strategy import ICTStrategy

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
SYMBOL = Symbol(name="EURUSD", pip_size=0.0001, digits=5, contract_size=100000)

# Fixed instant that IS inside the New York Open kill zone (13:00 UTC == 08:00 EST).
IN_KILL_ZONE_TS = datetime(2026, 1, 15, 13, 0, tzinfo=timezone.utc)
OUTSIDE_KILL_ZONE_TS = datetime(2026, 1, 15, 20, 0, tzinfo=timezone.utc)


def _dummy_candles(n: int = 60) -> list[Candle]:
    return [Candle(timestamp=BASE + timedelta(minutes=i), open=1.1, high=1.1005, low=1.0995, close=1.1, volume=100)
            for i in range(n)]


def _context(current_price: float, candles: list[Candle], as_of=IN_KILL_ZONE_TS) -> AnalysisContext:
    series = CandleSeries(symbol=SYMBOL, timeframe=Timeframe.M15, candles=candles)
    return AnalysisContext(
        symbol=SYMBOL, current_bid=current_price, current_ask=current_price, session="NewYork",
        higher_timeframe=series, middle_timeframe=series, entry_timeframe=series, as_of=as_of,
    )


def _patch_common(monkeypatch, *, direction=Direction.BUY, zone="discount", displacement=True,
                   fvgs=None, breakers=None, events=None, impulse_low=1.0900, impulse_event_price=1.1100):
    swing_low = SwingPoint(index=5, timestamp=BASE, price=impulse_low, kind="low")
    swing_high = SwingPoint(index=8, timestamp=BASE, price=1.1050, kind="high")
    swings = [swing_low, swing_high]
    default_event = StructureEvent(kind="CHoCH", direction=direction, timestamp=BASE,
                                    price=impulse_event_price, broken_level=1.1050, index=45)

    monkeypatch.setattr(ict_module, "atr", lambda candles, period=14: [0.0010] * len(candles))
    monkeypatch.setattr(ict_module, "find_swing_points", lambda candles, lookback=2: swings)
    monkeypatch.setattr(ict_module, "detect_structure_events", lambda candles, s: events if events is not None else [default_event])
    monkeypatch.setattr(ict_module, "is_displacement_candle", lambda candle, atr_value, mult: displacement)
    monkeypatch.setattr(ict_module, "find_fair_value_gaps", lambda candles: fvgs if fvgs is not None else [])
    monkeypatch.setattr(ict_module, "premium_discount_zone", lambda high, low, price: zone)
    monkeypatch.setattr(ict_module, "find_order_blocks", lambda candles, ev, lookback=15: [])
    monkeypatch.setattr(ict_module, "find_breaker_blocks", lambda candles, obs: breakers if breakers is not None else [])
    monkeypatch.setattr(ict_module, "find_liquidity_pools", lambda swings, tolerance, min_touches=2: [])
    return swing_low, swing_high


def test_ict_produces_buy_signal_inside_ote_zone(monkeypatch):
    # impulse: low=1.0900 -> event price 1.1100 (high). OTE zone (62%-79% retrace) of a 200-pip leg.
    _patch_common(monkeypatch, impulse_low=1.0900, impulse_event_price=1.1100)
    from core.algorithms.indicators.fibonacci import ote_zone
    zone = ote_zone(swing_high=1.1100, swing_low=1.0900, direction=Direction.BUY)
    mid_ote = zone.mid

    ctx = _context(current_price=mid_ote, candles=_dummy_candles())
    signal = ICTStrategy().analyze(ctx)

    assert signal is not None
    assert signal.direction == Direction.BUY
    assert any("kill zone" in r for r in signal.rationale)
    assert any("OTE" in r for r in signal.rationale)


def test_ict_rejects_outside_kill_zone(monkeypatch):
    _patch_common(monkeypatch)
    ctx = _context(current_price=1.098, candles=_dummy_candles(), as_of=OUTSIDE_KILL_ZONE_TS)

    assert ICTStrategy().analyze(ctx) is None


def test_ict_rejects_when_not_in_ote_or_fvg(monkeypatch):
    _patch_common(monkeypatch)
    ctx = _context(current_price=1.5000, candles=_dummy_candles())  # nowhere near OTE

    assert ICTStrategy().analyze(ctx) is None


def test_ict_accepts_fvg_entry_even_outside_ote(monkeypatch):
    from core.algorithms.structure.fair_value_gap import FVGZone
    fvg = FVGZone(direction=Direction.BUY, zone=PriceZone(1.4990, 1.5010), index=6, timestamp=BASE)
    _patch_common(monkeypatch, fvgs=[fvg])
    ctx = _context(current_price=1.5000, candles=_dummy_candles())  # far from OTE but inside the FVG

    signal = ICTStrategy().analyze(ctx)

    assert signal is not None
    assert signal.raw_score_components["fvg_confirmation"] is True


def test_ict_adds_confidence_for_breaker_block(monkeypatch):
    from core.algorithms.indicators.fibonacci import ote_zone
    zone = ote_zone(swing_high=1.1100, swing_low=1.0900, direction=Direction.BUY)
    breaker = BreakerBlock(direction=Direction.BUY, zone=PriceZone(zone.low - 0.001, zone.high + 0.001),
                            timestamp=BASE, index=30, source_order_block_index=20)
    _patch_common(monkeypatch, breakers=[breaker])
    ctx = _context(current_price=zone.mid, candles=_dummy_candles())

    signal = ICTStrategy().analyze(ctx)

    assert signal is not None
    assert signal.raw_score_components["liquidity_confirmation"] is True  # breaker confluence bonus
    assert any("Breaker Block" in r for r in signal.rationale)


def test_ict_rejects_buy_from_premium_zone(monkeypatch):
    from core.algorithms.indicators.fibonacci import ote_zone
    _patch_common(monkeypatch, zone="premium")
    zone = ote_zone(swing_high=1.1100, swing_low=1.0900, direction=Direction.BUY)
    ctx = _context(current_price=zone.mid, candles=_dummy_candles())

    assert ICTStrategy().analyze(ctx) is None


def test_ict_rejects_non_displacement_break(monkeypatch):
    from core.algorithms.indicators.fibonacci import ote_zone
    _patch_common(monkeypatch, displacement=False)
    zone = ote_zone(swing_high=1.1100, swing_low=1.0900, direction=Direction.BUY)
    ctx = _context(current_price=zone.mid, candles=_dummy_candles())

    assert ICTStrategy().analyze(ctx) is None


def test_ict_no_structure_events_returns_none(monkeypatch):
    _patch_common(monkeypatch, events=[])
    ctx = _context(current_price=1.10, candles=_dummy_candles())

    assert ICTStrategy().analyze(ctx) is None


def test_ict_strategy_is_registered():
    from core.strategies.registry import registry
    import core.strategies.ict  # noqa: F401

    ids = [m.strategy_id for m in registry.all()]
    assert "ict_ote_killzone" in ids
