"""Backtesting Engine: Point-in-Time correctness, multi-timeframe wiring,
outcome simulation, and strategy-combination support.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backtesting.engine import BacktestEngine
from backtesting.run_config import STRATEGY_COMBINATIONS, BacktestRunConfig
from core.context.analysis_context import AnalysisContext
from core.market_data.models import Candle, CandleSeries, Symbol, Tick, Timeframe
from core.market_data.provider_interface import MarketDataProvider
from core.signals.enums import Direction, StrategyCategory
from core.signals.strategy_signal import PriceZone, StrategySignal
from core.strategies.base import BaseStrategy
from core.strategies.registry import StrategyRegistry

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
SYMBOL = Symbol(name="EURUSD", pip_size=0.0001, digits=5, contract_size=100000)


class _FakeProvider(MarketDataProvider):
    """Serves a fixed candle series per timeframe so the test can tell
    Higher/Middle/Entry requests apart."""

    def __init__(self, entry_candles: list[Candle]):
        self._entry_candles = entry_candles

    def is_connected(self) -> bool:
        return True

    def get_symbol_info(self, symbol_name: str) -> Symbol:
        return SYMBOL

    def get_ohlcv(self, symbol, timeframe, count):
        return CandleSeries(symbol=symbol, timeframe=timeframe, candles=self._entry_candles)

    def get_ticks(self, symbol, start, end):
        return []

    def get_latest_tick(self, symbol):
        return Tick(timestamp=self._entry_candles[-1].timestamp, bid=self._entry_candles[-1].close,
                    ask=self._entry_candles[-1].close)


class _RecordingStrategy(BaseStrategy):
    strategy_id = "recording_dummy"
    category = StrategyCategory.CLASSIC

    def __init__(self, fixed_signal_factory):
        self.seen_as_of: list[datetime] = []
        self.seen_last_visible_timestamps: list[datetime] = []
        self.seen_entry_lengths: list[int] = []
        self._fixed_signal_factory = fixed_signal_factory

    def analyze(self, context: AnalysisContext) -> StrategySignal | None:
        self.seen_as_of.append(context.as_of)
        last_visible = context.entry_timeframe.candles[-1].timestamp if context.entry_timeframe.candles else None
        self.seen_last_visible_timestamps.append(last_visible)
        self.seen_entry_lengths.append(len(context.entry_timeframe.candles))
        return self._fixed_signal_factory(context)


def _make_candles(n: int, start_price: float = 1.1000, step: float = 0.0005) -> list[Candle]:
    price = start_price
    candles = []
    for i in range(n):
        price += step
        candles.append(Candle(timestamp=BASE + timedelta(minutes=15 * i), open=price - 0.0002, high=price + 0.0003,
                               low=price - 0.0003, close=price, volume=100))
    return candles


class _FakeRegistry(StrategyRegistry):
    def __init__(self, strategy_instance: BaseStrategy):
        super().__init__()
        self._instance = strategy_instance
        self.register(type(strategy_instance))

    def enabled_by_category(self, categories=None):
        return [lambda inst=self._instance: inst]  # calling it returns the same recorded instance


def _make_engine_with_recording_strategy(candles, fixed_signal_factory, lookback_bars=None):
    strategy = _RecordingStrategy(fixed_signal_factory)
    registry = _FakeRegistry(strategy)
    provider = _FakeProvider(candles)

    from core.confidence.confidence_engine import ConfidenceEngine
    from core.selection.strategy_selection_engine import StrategySelectionEngine

    confidence_engine = ConfidenceEngine(thresholds={"weak_max": 49, "medium_max": 74}, multi_strategy_agreement_bonus=10)
    selection_engine = StrategySelectionEngine(confidence_engine=confidence_engine, filters=[], min_risk_reward=1.0)
    engine = BacktestEngine(provider=provider, registry=registry, selection_engine=selection_engine,
                             lookback_bars=lookback_bars)
    return engine, strategy


def test_point_in_time_never_exposes_future_candles():
    candles = _make_candles(20)

    def no_signal(context):
        return None

    engine, strategy = _make_engine_with_recording_strategy(candles, no_signal)
    config = BacktestRunConfig(symbol_name="EURUSD", entry_timeframe=Timeframe.M15, strategy_set="Classic",
                                start=candles[5].timestamp, end=candles[15].timestamp)

    engine.run(config)

    assert len(strategy.seen_as_of) > 0
    for as_of, last_visible in zip(strategy.seen_as_of, strategy.seen_last_visible_timestamps):
        assert last_visible <= as_of, "strategy was shown a candle from after the simulated 'now'"


def test_outcome_simulation_uses_only_future_candles_after_entry():
    candles = _make_candles(30, start_price=1.1000, step=0.0)  # flat except manual spikes below
    # inject a clear TP1 hit two candles after a chosen entry point
    candles[12] = Candle(timestamp=candles[12].timestamp, open=1.10, high=1.115, low=1.099, close=1.10, volume=100)

    def buy_signal_at_index_10(context: AnalysisContext):
        if context.as_of != candles[10].timestamp:
            return None
        return StrategySignal(
            strategy_id="recording_dummy", category=StrategyCategory.CLASSIC, direction=Direction.BUY,
            suggested_entry_zone=PriceZone(1.10, 1.10), suggested_stop_loss=1.095,
            suggested_take_profit_1=1.11, suggested_take_profit_2=1.12, rationale=["fixture"],
            raw_score_components={"base_confidence": 80},
        )

    engine, strategy = _make_engine_with_recording_strategy(candles, buy_signal_at_index_10)
    config = BacktestRunConfig(symbol_name="EURUSD", entry_timeframe=Timeframe.M15, strategy_set="Classic",
                                start=candles[10].timestamp, end=candles[20].timestamp)

    report = engine.run(config)

    assert report.total_setups == 1
    assert report.outcomes[0].hit == "TP1"
    assert report.outcomes[0].r_multiple == pytest.approx(2.0)  # (1.11-1.10)/(1.10-1.095)
    assert report.outcomes[0].closed_at == candles[12].timestamp


def test_sl_outcome_records_minus_one_r_and_none_records_zero():
    candles = _make_candles(30, start_price=1.1000, step=0.0)
    candles[11] = Candle(timestamp=candles[11].timestamp, open=1.10, high=1.101, low=1.090, close=1.10, volume=100)

    def buy_signal_at_index_10(context):
        if context.as_of != candles[10].timestamp:
            return None
        return StrategySignal(
            strategy_id="recording_dummy", category=StrategyCategory.CLASSIC, direction=Direction.BUY,
            suggested_entry_zone=PriceZone(1.10, 1.10), suggested_stop_loss=1.095,
            suggested_take_profit_1=1.11, suggested_take_profit_2=1.12, rationale=["fixture"],
            raw_score_components={"base_confidence": 80},
        )

    engine, _ = _make_engine_with_recording_strategy(candles, buy_signal_at_index_10)
    config = BacktestRunConfig(symbol_name="EURUSD", entry_timeframe=Timeframe.M15, strategy_set="Classic",
                                start=candles[10].timestamp, end=candles[20].timestamp)

    report = engine.run(config)

    assert report.outcomes[0].hit == "SL"
    assert report.outcomes[0].r_multiple == -1.0
    assert report.outcomes[0].closed_at == candles[11].timestamp


def test_none_outcome_records_no_closed_at():
    """A trade still open when the run window ends must not fabricate a
    resolution timestamp — closed_at stays None, symmetric with hit="NONE"
    excluding it from every R-based statistic."""
    candles = _make_candles(15, start_price=1.1000, step=0.0)  # never moves enough to hit SL/TP

    def buy_signal_at_index_10(context):
        if context.as_of != candles[10].timestamp:
            return None
        return StrategySignal(
            strategy_id="recording_dummy", category=StrategyCategory.CLASSIC, direction=Direction.BUY,
            suggested_entry_zone=PriceZone(1.10, 1.10), suggested_stop_loss=1.050,
            suggested_take_profit_1=1.20, suggested_take_profit_2=1.30, rationale=["fixture"],
            raw_score_components={"base_confidence": 80},
        )

    engine, _ = _make_engine_with_recording_strategy(candles, buy_signal_at_index_10)
    config = BacktestRunConfig(symbol_name="EURUSD", entry_timeframe=Timeframe.M15, strategy_set="Classic",
                                start=candles[10].timestamp, end=candles[14].timestamp)

    report = engine.run(config)

    assert report.outcomes[0].hit == "NONE"
    assert report.outcomes[0].closed_at is None


def test_min_confidence_filters_out_low_confidence_setups():
    candles = _make_candles(20)

    def low_confidence_signal(context):
        return StrategySignal(
            strategy_id="recording_dummy", category=StrategyCategory.CLASSIC, direction=Direction.BUY,
            suggested_entry_zone=PriceZone(1.10, 1.10), suggested_stop_loss=1.095,
            suggested_take_profit_1=1.11, suggested_take_profit_2=1.12, rationale=["fixture"],
            raw_score_components={"base_confidence": 40},  # below the 50 threshold below
        )

    strategy = _RecordingStrategy(low_confidence_signal)
    registry = _FakeRegistry(strategy)
    provider = _FakeProvider(candles)
    from core.confidence.confidence_engine import ConfidenceEngine
    from core.selection.strategy_selection_engine import StrategySelectionEngine
    confidence_engine = ConfidenceEngine(thresholds={"weak_max": 49, "medium_max": 74}, multi_strategy_agreement_bonus=10)
    selection_engine = StrategySelectionEngine(confidence_engine=confidence_engine, filters=[], min_risk_reward=1.0)

    unfiltered = BacktestEngine(provider=provider, registry=registry, selection_engine=selection_engine)
    filtered = BacktestEngine(provider=provider, registry=registry, selection_engine=selection_engine, min_confidence=50)

    config = BacktestRunConfig(symbol_name="EURUSD", entry_timeframe=Timeframe.M15, strategy_set="Classic",
                                start=candles[5].timestamp, end=candles[15].timestamp)

    assert unfiltered.run(config).total_setups > 0
    assert filtered.run(config).total_setups == 0


def test_multi_timeframe_config_fetches_different_series_for_higher_middle():
    candles = _make_candles(20)
    requested_timeframes = []

    class _TrackingProvider(_FakeProvider):
        def get_ohlcv(self, symbol, timeframe, count):
            requested_timeframes.append(timeframe)
            return super().get_ohlcv(symbol, timeframe, count)

    provider = _TrackingProvider(candles)
    strategy = _RecordingStrategy(lambda ctx: None)
    registry = _FakeRegistry(strategy)

    from core.confidence.confidence_engine import ConfidenceEngine
    from core.selection.strategy_selection_engine import StrategySelectionEngine
    confidence_engine = ConfidenceEngine(thresholds={"weak_max": 49, "medium_max": 74}, multi_strategy_agreement_bonus=10)
    selection_engine = StrategySelectionEngine(confidence_engine=confidence_engine, filters=[], min_risk_reward=1.0)

    timeframes_config = {"default_mapping": {"higher": "H4", "middle": "H1", "entry": "M15"}, "selection_rules": []}
    engine = BacktestEngine(provider=provider, registry=registry, selection_engine=selection_engine,
                             timeframes_config=timeframes_config)
    config = BacktestRunConfig(symbol_name="EURUSD", entry_timeframe=Timeframe.M15, strategy_set="Classic",
                                start=candles[5].timestamp, end=candles[10].timestamp)

    engine.run(config)

    assert Timeframe.H4 in requested_timeframes
    assert Timeframe.H1 in requested_timeframes
    assert Timeframe.M15 in requested_timeframes


def test_all_seven_strategy_combinations_are_defined():
    assert set(STRATEGY_COMBINATIONS.keys()) == {
        "Classic", "SMC", "ICT", "Classic+SMC", "Classic+ICT", "SMC+ICT", "All",
    }


def test_backtest_run_config_categories_property():
    config = BacktestRunConfig(symbol_name="EURUSD", entry_timeframe=Timeframe.M15, strategy_set="Classic+ICT",
                                start=BASE, end=BASE)
    assert config.categories == {StrategyCategory.CLASSIC, StrategyCategory.ICT}

    all_config = BacktestRunConfig(symbol_name="EURUSD", entry_timeframe=Timeframe.M15, strategy_set="All",
                                    start=BASE, end=BASE)
    assert all_config.categories is None


def test_lookback_bars_bounds_the_visible_window_without_breaking_point_in_time():
    """Without a bound, the entry series a strategy sees grows on every
    single simulated bar (unbounded — and, since several algorithms rescan
    the whole visible window each call, the reason a real multi-year
    backtest was impractically slow before this was added). With a bound,
    the window must never exceed it, while Point-in-Time (never seeing a
    future candle) still holds."""
    candles = _make_candles(30)

    def no_signal(context):
        return None

    engine, strategy = _make_engine_with_recording_strategy(
        candles, no_signal, lookback_bars={"higher": 5, "middle": 5, "entry": 5}
    )
    config = BacktestRunConfig(symbol_name="EURUSD", entry_timeframe=Timeframe.M15, strategy_set="Classic",
                                start=candles[10].timestamp, end=candles[25].timestamp)

    engine.run(config)

    assert len(strategy.seen_entry_lengths) > 0
    assert max(strategy.seen_entry_lengths) <= 5
    for as_of, last_visible in zip(strategy.seen_as_of, strategy.seen_last_visible_timestamps):
        assert last_visible <= as_of  # bounding must not break Point-in-Time


def test_same_candle_sl_and_tp_both_touched_resolves_as_sl():
    """OHLC data cannot establish true intrabar order -- backtesting/engine
    .py's documented, deterministic convention is SL-before-TP whenever a
    single candle's range covers both. Regression test for that policy."""
    candles = _make_candles(20, start_price=1.1000, step=0.0)
    # candle[11]'s range covers both the SL (1.095) and TP1 (1.11) of the signal below.
    candles[11] = Candle(timestamp=candles[11].timestamp, open=1.10, high=1.12, low=1.09, close=1.10, volume=100)

    def buy_signal_at_index_10(context):
        if context.as_of != candles[10].timestamp:
            return None
        return StrategySignal(
            strategy_id="recording_dummy", category=StrategyCategory.CLASSIC, direction=Direction.BUY,
            suggested_entry_zone=PriceZone(1.10, 1.10), suggested_stop_loss=1.095,
            suggested_take_profit_1=1.11, suggested_take_profit_2=1.12, rationale=["fixture"],
            raw_score_components={"base_confidence": 80},
        )

    engine, _ = _make_engine_with_recording_strategy(candles, buy_signal_at_index_10)
    config = BacktestRunConfig(symbol_name="EURUSD", entry_timeframe=Timeframe.M15, strategy_set="Classic",
                                start=candles[10].timestamp, end=candles[15].timestamp)

    report = engine.run(config)

    assert report.outcomes[0].hit == "SL"
    assert report.outcomes[0].r_multiple == -1.0


def test_rejected_min_rr_setup_is_never_counted_as_a_trade():
    """A setup that fails the min-R:R floor comes back from
    StrategySelectionEngine with status=REJECTED_MIN_RR rather than None --
    BacktestEngine must never turn that into a TradeOutcome."""
    candles = _make_candles(20)

    def low_rr_signal(context):
        # R:R = (1.101-1.10)/(1.10-1.095) = 0.2 -- well under the 1.5 floor below.
        return StrategySignal(
            strategy_id="recording_dummy", category=StrategyCategory.CLASSIC, direction=Direction.BUY,
            suggested_entry_zone=PriceZone(1.10, 1.10), suggested_stop_loss=1.095,
            suggested_take_profit_1=1.101, suggested_take_profit_2=1.102, rationale=["fixture"],
            raw_score_components={"base_confidence": 80},
        )

    strategy = _RecordingStrategy(low_rr_signal)
    registry = _FakeRegistry(strategy)
    provider = _FakeProvider(candles)
    from core.confidence.confidence_engine import ConfidenceEngine
    from core.selection.strategy_selection_engine import StrategySelectionEngine
    confidence_engine = ConfidenceEngine(thresholds={"weak_max": 49, "medium_max": 74}, multi_strategy_agreement_bonus=10)
    # min_risk_reward=1.5 -- the production floor this test's signal (R:R=0.2) fails.
    selection_engine = StrategySelectionEngine(confidence_engine=confidence_engine, filters=[], min_risk_reward=1.5)
    engine = BacktestEngine(provider=provider, registry=registry, selection_engine=selection_engine)
    config = BacktestRunConfig(symbol_name="EURUSD", entry_timeframe=Timeframe.M15, strategy_set="Classic",
                                start=candles[5].timestamp, end=candles[15].timestamp)

    # Sanity: the underlying selection engine really does produce a rejected
    # (not None) setup for this signal -- otherwise this test would pass for
    # the wrong reason.
    raw_setup = selection_engine.run([strategy], AnalysisContext(
        symbol=SYMBOL, current_bid=1.10, current_ask=1.10, session="unspecified",
        higher_timeframe=CandleSeries(symbol=SYMBOL, timeframe=Timeframe.M15, candles=candles),
        middle_timeframe=CandleSeries(symbol=SYMBOL, timeframe=Timeframe.M15, candles=candles),
        entry_timeframe=CandleSeries(symbol=SYMBOL, timeframe=Timeframe.M15, candles=candles),
        as_of=candles[-1].timestamp,
    ))
    assert raw_setup is not None
    from core.signals.enums import SetupStatus
    assert raw_setup.status == SetupStatus.REJECTED_MIN_RR

    report = engine.run(config)
    assert report.total_setups == 0


def test_no_lookback_bars_keeps_the_old_unbounded_behavior():
    candles = _make_candles(30)

    def no_signal(context):
        return None

    engine, strategy = _make_engine_with_recording_strategy(candles, no_signal, lookback_bars=None)
    config = BacktestRunConfig(symbol_name="EURUSD", entry_timeframe=Timeframe.M15, strategy_set="Classic",
                                start=candles[10].timestamp, end=candles[25].timestamp)

    engine.run(config)

    assert max(strategy.seen_entry_lengths) > 5  # grows past any small bound when none is configured
