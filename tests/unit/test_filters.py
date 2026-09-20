"""Unit tests for the cross-cutting Filter implementations
(core/filters/*.py) — each wired into production via
backend/dependencies.py or documented as a tested-but-not-adopted
CURRENT-vs-MODIFIED comparison. Exercised directly here rather than only
through the higher-level integration test, since these are reusable
building blocks other filters/strategies may also depend on.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.context.analysis_context import AnalysisContext
from core.filters.htf_trend_alignment_filter import HTFTrendAlignmentFilter
from core.filters.volatility_regime_filter import VolatilityRegimeFilter
from core.market_data.models import Candle, CandleSeries, Symbol, Timeframe
from core.signals.enums import Direction, StrategyCategory
from core.signals.strategy_signal import PriceZone, StrategySignal

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
SYMBOL = Symbol(name="EURUSD", pip_size=0.0001, digits=5, contract_size=100000)


def _signal(direction: Direction) -> StrategySignal:
    return StrategySignal(
        strategy_id="fixture", category=StrategyCategory.CLASSIC, direction=direction,
        suggested_entry_zone=PriceZone(1.1000, 1.1000), suggested_stop_loss=1.0950,
        suggested_take_profit_1=1.1075, suggested_take_profit_2=1.1150,
        rationale=["fixture"], raw_score_components={"base_confidence": 70}, generated_at=BASE,
    )


def _context(entry_candles: list[Candle], higher_candles: list[Candle] | None = None) -> AnalysisContext:
    entry_series = CandleSeries(symbol=SYMBOL, timeframe=Timeframe.M15, candles=entry_candles)
    higher_series = CandleSeries(symbol=SYMBOL, timeframe=Timeframe.H4, candles=higher_candles or entry_candles)
    return AnalysisContext(
        symbol=SYMBOL, current_bid=1.1000, current_ask=1.1000, session="London",
        higher_timeframe=higher_series, middle_timeframe=entry_series, entry_timeframe=entry_series, as_of=entry_candles[-1].timestamp,
    )


# ---------------------------------------------------------------------------
# VolatilityRegimeFilter
# ---------------------------------------------------------------------------

def _flat_candles(n: int) -> list[Candle]:
    return [Candle(timestamp=BASE + timedelta(minutes=i), open=1.1000, high=1.1001, low=1.0999, close=1.1000, volume=100)
            for i in range(n)]


def _growing_range_candles(n: int) -> list[Candle]:
    candles = _flat_candles(40)
    for i in range(n):
        r = 0.0005 + i * 0.0005
        candles.append(Candle(timestamp=BASE + timedelta(minutes=40 + i), open=1.1000, high=1.1000 + r,
                               low=1.1000 - r, close=1.1000, volume=100))
    return candles


def test_volatility_filter_passes_low_volatility():
    context = _context(_flat_candles(60))
    result = VolatilityRegimeFilter().apply(_signal(Direction.BUY), context)
    assert result.passed


def test_volatility_filter_rejects_high_volatility():
    context = _context(_growing_range_candles(20))
    result = VolatilityRegimeFilter().apply(_signal(Direction.BUY), context)
    assert not result.passed
    assert "high" in result.reason


def test_volatility_filter_custom_reject_regimes():
    context = _context(_flat_candles(60))
    strict = VolatilityRegimeFilter(reject_regimes=frozenset({"low", "medium", "high"}))
    assert not strict.apply(_signal(Direction.BUY), context).passed


# ---------------------------------------------------------------------------
# HTFTrendAlignmentFilter
# ---------------------------------------------------------------------------

def _uptrend_candles(n: int = 80) -> list[Candle]:
    candles = []
    price = 1.1000
    for i in range(n):
        price += 0.0010
        candles.append(Candle(timestamp=BASE + timedelta(hours=4 * i), open=price - 0.0005, high=price + 0.0005,
                               low=price - 0.0010, close=price, volume=100))
    return candles


def test_htf_filter_passes_signal_aligned_with_higher_timeframe_uptrend():
    context = _context(_flat_candles(60), higher_candles=_uptrend_candles())
    result = HTFTrendAlignmentFilter().apply(_signal(Direction.BUY), context)
    assert result.passed


def test_htf_filter_rejects_signal_against_higher_timeframe_uptrend():
    context = _context(_flat_candles(60), higher_candles=_uptrend_candles())
    result = HTFTrendAlignmentFilter().apply(_signal(Direction.SELL), context)
    assert not result.passed
    assert "conflicts" in result.reason


def test_htf_filter_passes_through_when_no_clear_higher_timeframe_trend():
    """Short/insufficient higher-timeframe history -> detect_trend returns
    direction=None -> the filter must not block for lack of confirmation,
    only for active conflict (see the filter's own docstring)."""
    context = _context(_flat_candles(60), higher_candles=_flat_candles(10))
    result = HTFTrendAlignmentFilter().apply(_signal(Direction.SELL), context)
    assert result.passed
