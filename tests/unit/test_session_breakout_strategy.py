"""SessionBreakoutStrategy tests.

Unlike Classic/SMC/ICT/SweepDisplacement, the core logic under test here
IS the timestamp-based Asian-range/session-window computation, so real
datetime-crafted candles are used rather than mocking that away — only
`atr`, `find_swing_points` and `is_displacement_candle` are monkeypatched
for determinism (liquidity-pool TP targeting is already covered by the
other strategies' tests).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import core.strategies.session_breakout.session_breakout_strategy as sb_module
from core.confidence.component_scoring import ComponentWeights
from core.context.analysis_context import AnalysisContext
from core.market_data.models import Candle, CandleSeries, Symbol, Timeframe
from core.signals.enums import Direction
from core.strategies.session_breakout.session_breakout_strategy import (
    GATE_DISPLACEMENT,
    GATE_SESSION_WINDOW,
    SessionBreakoutStrategy,
)

DAY = date(2026, 1, 5)
SYMBOL = Symbol(name="EURUSD", pip_size=0.0001, digits=5, contract_size=100000)
ASIAN_HIGH = 1.1020
ASIAN_LOW = 1.0980


def _dt(hour: int, minute: int) -> datetime:
    return datetime(DAY.year, DAY.month, DAY.day, hour, minute, tzinfo=timezone.utc)


def _build_candles(breakout_time: tuple[int, int] = (7, 0), breakout_close: float = 1.1050) -> list[Candle]:
    candles: list[Candle] = []
    # 40 filler candles the previous "day" (irrelevant to Asian-range computation, just padding for min_lookback_bars)
    filler_start = _dt(0, 0) - timedelta(hours=10)
    for i in range(40):
        ts = filler_start + timedelta(minutes=15 * i)
        candles.append(Candle(timestamp=ts, open=1.1000, high=1.1005, low=1.0995, close=1.1000, volume=100))
    # Asian session candles: 00:00 (inclusive) to 06:45 (28 x M15, ends before 07:00)
    for i in range(28):
        ts = _dt(0, 0) + timedelta(minutes=15 * i)
        candles.append(Candle(timestamp=ts, open=1.1000, high=ASIAN_HIGH, low=ASIAN_LOW, close=1.1000, volume=100))
    # Breakout candle
    bt_hour, bt_minute = breakout_time
    candles.append(Candle(timestamp=_dt(bt_hour, bt_minute), open=1.1010, high=max(1.1010, breakout_close) + 0.0005,
                           low=min(1.1010, breakout_close) - 0.0005, close=breakout_close, volume=150))
    return candles


def _context(candles: list[Candle]) -> AnalysisContext:
    series = CandleSeries(symbol=SYMBOL, timeframe=Timeframe.M15, candles=candles)
    price = candles[-1].close
    return AnalysisContext(
        symbol=SYMBOL, current_bid=price, current_ask=price, session="London",
        higher_timeframe=series, middle_timeframe=series, entry_timeframe=series, as_of=candles[-1].timestamp,
    )


def _patch(monkeypatch, *, displacement: bool = True):
    monkeypatch.setattr(sb_module, "atr", lambda candles, period=14: [0.0020] * len(candles))
    monkeypatch.setattr(sb_module, "find_swing_points", lambda candles, lookback=2: [])
    monkeypatch.setattr(sb_module, "is_displacement_candle", lambda candle, atr_value, mult: displacement)


def test_no_trade_during_asian_session_itself(monkeypatch):
    _patch(monkeypatch)
    candles = _build_candles(breakout_time=(3, 0), breakout_close=1.1050)
    # as_of is 03:00, inside the Asian session -> session window gate must reject regardless of price
    strategy = SessionBreakoutStrategy()

    assert strategy.analyze(_context(candles)) is None


def test_no_trade_when_price_stays_inside_asian_range(monkeypatch):
    _patch(monkeypatch)
    candles = _build_candles(breakout_time=(7, 0), breakout_close=1.1000)  # inside [ASIAN_LOW, ASIAN_HIGH]

    strategy = SessionBreakoutStrategy()

    assert strategy.analyze(_context(candles)) is None


def test_breakout_above_asian_high_produces_buy(monkeypatch):
    _patch(monkeypatch)
    candles = _build_candles(breakout_time=(7, 0), breakout_close=1.1050)

    strategy = SessionBreakoutStrategy()
    result = strategy.analyze(_context(candles))

    assert result is not None
    assert result.direction == Direction.BUY
    assert result.suggested_stop_loss < ASIAN_LOW


def test_breakout_below_asian_low_produces_sell(monkeypatch):
    _patch(monkeypatch)
    candles = _build_candles(breakout_time=(7, 0), breakout_close=1.0950)

    strategy = SessionBreakoutStrategy()
    result = strategy.analyze(_context(candles))

    assert result is not None
    assert result.direction == Direction.SELL
    assert result.suggested_stop_loss > ASIAN_HIGH


def test_displacement_gate_blocks_weak_breakout_by_default(monkeypatch):
    _patch(monkeypatch, displacement=False)
    candles = _build_candles(breakout_time=(7, 0), breakout_close=1.1050)

    strategy = SessionBreakoutStrategy()

    assert strategy.analyze(_context(candles)) is None


def test_displacement_gate_can_be_disabled_for_ablation(monkeypatch):
    _patch(monkeypatch, displacement=False)
    candles = _build_candles(breakout_time=(7, 0), breakout_close=1.1050)

    strategy = SessionBreakoutStrategy(disabled_components=frozenset({GATE_DISPLACEMENT}))

    assert strategy.analyze(_context(candles)) is not None


def test_outside_london_window_rejected_even_with_gate_disabled(monkeypatch):
    """Disabling the session-window gate only lifts the London-hours
    requirement, not the requirement that the Asian range has actually
    closed -- trading during the Asian session itself is never valid."""
    _patch(monkeypatch)
    candles = _build_candles(breakout_time=(3, 0), breakout_close=1.1050)

    strategy = SessionBreakoutStrategy(disabled_components=frozenset({GATE_SESSION_WINDOW}))

    assert strategy.analyze(_context(candles)) is None


def test_session_window_gate_disabled_allows_afternoon_breakout(monkeypatch):
    _patch(monkeypatch)
    candles = _build_candles(breakout_time=(14, 0), breakout_close=1.1050)

    strategy_default = SessionBreakoutStrategy()
    strategy_disabled = SessionBreakoutStrategy(disabled_components=frozenset({GATE_SESSION_WINDOW}))

    assert strategy_default.analyze(_context(candles)) is None
    assert strategy_disabled.analyze(_context(candles)) is not None


def test_custom_weights_change_confidence_score(monkeypatch):
    _patch(monkeypatch)
    candles = _build_candles(breakout_time=(7, 0), breakout_close=1.1050)

    default_result = SessionBreakoutStrategy().analyze(_context(candles))
    weighted_result = SessionBreakoutStrategy(
        weights=ComponentWeights({"range_quality": 1.0, "breakout_strength": 0.0, "displacement_strength": 0.0, "session_timing": 0.0})
    ).analyze(_context(candles))

    assert default_result is not None and weighted_result is not None
    assert default_result.raw_score_components["base_confidence"] != weighted_result.raw_score_components["base_confidence"]
