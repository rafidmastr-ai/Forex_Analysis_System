"""Regression test for the point-in-time fix to CandleSeries.sliced_as_of /
BacktestEngine (see core/market_data/models.py and backtesting/engine.py):
a still-FORMING Higher-timeframe candle must never be visible to a
strategy before it has actually closed, even though its stored OHLC
already reflects the whole (partly future, from the decision's own
perspective) bar.

Unlike tests/unit/test_backtesting_engine.py's `_FakeProvider` (which
deliberately serves the SAME M15-spaced candle list regardless of the
requested timeframe, and therefore can't exercise this bug at all), this
test's provider returns genuinely different, correctly-spaced series per
timeframe -- exactly like the real HistoricalFileMarketDataProvider and
MockMarketDataProvider do.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backtesting.engine import BacktestEngine
from backtesting.run_config import BacktestRunConfig
from core.confidence.confidence_engine import ConfidenceEngine
from core.context.analysis_context import AnalysisContext
from core.market_data.models import Candle, CandleSeries, Symbol, Tick, Timeframe
from core.market_data.provider_interface import MarketDataProvider
from core.selection.strategy_selection_engine import StrategySelectionEngine
from core.signals.enums import StrategyCategory
from core.strategies.base import BaseStrategy
from core.strategies.registry import StrategyRegistry

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
SYMBOL = Symbol(name="EURUSD", pip_size=0.0001, digits=5, contract_size=100000)

# A H4 candle opening at 08:00 (closes 12:00) carries an obviously-fake,
# easily-identified "secret future" high -- if this value is ever visible
# to a decision made before 12:00, the bug has regressed.
SECRET_FUTURE_HIGH = 9999.0


def _h4_candles() -> list[Candle]:
    candles = []
    for i in range(6):  # 00:00, 04:00, 08:00, 12:00, 16:00, 20:00
        ts = BASE + timedelta(hours=4 * i)
        high = SECRET_FUTURE_HIGH if ts == BASE + timedelta(hours=8) else 1.1050
        candles.append(Candle(timestamp=ts, open=1.1000, high=high, low=1.0950, close=1.1010, volume=100))
    return candles


def _m15_candles() -> list[Candle]:
    # 07:00 through 13:00 in M15 steps -- straddles the 08:00-12:00 H4 bar.
    candles = []
    n = int((6 * 60) / 15) + 1
    start = BASE + timedelta(hours=7)
    for i in range(n):
        ts = start + timedelta(minutes=15 * i)
        candles.append(Candle(timestamp=ts, open=1.1000, high=1.1005, low=1.0995, close=1.1002, volume=50))
    return candles


class _PerTimeframeProvider(MarketDataProvider):
    def __init__(self):
        self._series = {Timeframe.M15: _m15_candles(), Timeframe.H4: _h4_candles(), Timeframe.H1: _m15_candles()}

    def is_connected(self) -> bool:
        return True

    def get_symbol_info(self, symbol_name: str) -> Symbol:
        return SYMBOL

    def get_ohlcv(self, symbol, timeframe, count):
        return CandleSeries(symbol=symbol, timeframe=timeframe, candles=self._series[timeframe])

    def get_ticks(self, symbol, start, end):
        return []

    def get_latest_tick(self, symbol):
        last = self._series[Timeframe.M15][-1]
        return Tick(timestamp=last.timestamp, bid=last.close, ask=last.close)


class _HigherTimeframeRecorder(BaseStrategy):
    strategy_id = "higher_tf_recorder"
    category = StrategyCategory.CLASSIC

    def __init__(self):
        self.seen: list[tuple[datetime, float | None]] = []

    def analyze(self, context: AnalysisContext):
        highs = [c.high for c in context.higher_timeframe.candles]
        self.seen.append((context.as_of, max(highs) if highs else None))
        return None


class _FixedRegistry(StrategyRegistry):
    def __init__(self, instance: BaseStrategy):
        super().__init__()
        self._instance = instance

    def enabled_by_category(self, categories=None):
        return [lambda inst=self._instance: inst]


def _run() -> _HigherTimeframeRecorder:
    provider = _PerTimeframeProvider()
    strategy = _HigherTimeframeRecorder()
    registry = _FixedRegistry(strategy)
    confidence_engine = ConfidenceEngine(thresholds={"weak_max": 49, "medium_max": 74}, multi_strategy_agreement_bonus=10)
    selection_engine = StrategySelectionEngine(confidence_engine=confidence_engine, filters=[], min_risk_reward=1.0)
    timeframes_config = {"default_mapping": {"higher": "H4", "middle": "H1", "entry": "M15"}, "selection_rules": []}
    engine = BacktestEngine(provider=provider, registry=registry, selection_engine=selection_engine,
                             timeframes_config=timeframes_config)
    m15 = provider.get_ohlcv(SYMBOL, Timeframe.M15, 0).candles
    config = BacktestRunConfig(symbol_name="EURUSD", entry_timeframe=Timeframe.M15, strategy_set="Classic",
                                start=m15[0].timestamp, end=m15[-1].timestamp)
    engine.run(config)
    return strategy


def test_still_forming_higher_timeframe_candle_is_never_visible_before_it_closes():
    strategy = _run()
    assert len(strategy.seen) > 0

    h4_close_instant = BASE + timedelta(hours=12)  # the 08:00-12:00 H4 candle closes at 12:00
    m15_minutes = timedelta(minutes=Timeframe.M15.minutes)
    # Each decision's own true "as of" instant is the M15 entry candle's CLOSE
    # (open + 15min), not its open -- see backtesting/engine.py's fix.
    before_close = [(as_of, high) for as_of, high in strategy.seen if as_of + m15_minutes < h4_close_instant]
    at_or_after_close = [(as_of, high) for as_of, high in strategy.seen if as_of + m15_minutes >= h4_close_instant]

    assert before_close, "test setup produced no decisions before the H4 candle's close"
    assert at_or_after_close, "test setup produced no decisions at/after the H4 candle's close"

    for as_of, highest_visible in before_close:
        assert highest_visible != SECRET_FUTURE_HIGH, (
            f"look-ahead: at {as_of} (before the forming H4 candle closes at {h4_close_instant}), "
            f"the strategy could see the still-future high {SECRET_FUTURE_HIGH}"
        )

    assert any(high == SECRET_FUTURE_HIGH for _, high in at_or_after_close), (
        "the H4 candle should become visible once it has actually closed at 12:00"
    )


def test_entry_timeframe_series_still_includes_its_own_just_closed_candle():
    """The point-in-time fix must not regress the entry timeframe's own
    visibility: at the instant an entry candle 'closes' (its close price is
    what current_bid/ask use), that SAME candle must still be the most
    recent one visible in entry_timeframe -- only coarser (Higher/Middle)
    series were ever affected by the bug."""
    provider = _PerTimeframeProvider()
    m15 = provider.get_ohlcv(SYMBOL, Timeframe.M15, 0).candles

    # Re-run with an entry-series recorder instead, to check entry visibility directly.
    class _EntryRecorder(BaseStrategy):
        strategy_id = "entry_recorder"
        category = StrategyCategory.CLASSIC

        def __init__(self):
            self.seen_last_entry_ts: list[datetime] = []

        def analyze(self, context: AnalysisContext):
            self.seen_last_entry_ts.append(context.entry_timeframe.candles[-1].timestamp)
            return None

    entry_strategy = _EntryRecorder()
    registry = _FixedRegistry(entry_strategy)
    confidence_engine = ConfidenceEngine(thresholds={"weak_max": 49, "medium_max": 74}, multi_strategy_agreement_bonus=10)
    selection_engine = StrategySelectionEngine(confidence_engine=confidence_engine, filters=[], min_risk_reward=1.0)
    timeframes_config = {"default_mapping": {"higher": "H4", "middle": "H1", "entry": "M15"}, "selection_rules": []}
    engine = BacktestEngine(provider=provider, registry=registry, selection_engine=selection_engine,
                             timeframes_config=timeframes_config)
    config = BacktestRunConfig(symbol_name="EURUSD", entry_timeframe=Timeframe.M15, strategy_set="Classic",
                                start=m15[0].timestamp, end=m15[-1].timestamp)
    engine.run(config)

    assert len(entry_strategy.seen_last_entry_ts) == len(m15)
    for candle, last_visible in zip(m15, entry_strategy.seen_last_entry_ts):
        assert last_visible == candle.timestamp
