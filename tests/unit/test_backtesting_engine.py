"""Backtesting Engine: Point-in-Time correctness, multi-timeframe wiring,
outcome simulation, and strategy-combination support.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

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
        self._fixed_signal_factory = fixed_signal_factory

    def analyze(self, context: AnalysisContext) -> StrategySignal | None:
        self.seen_as_of.append(context.as_of)
        last_visible = context.entry_timeframe.candles[-1].timestamp if context.entry_timeframe.candles else None
        self.seen_last_visible_timestamps.append(last_visible)
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


def _make_engine_with_recording_strategy(candles, fixed_signal_factory):
    strategy = _RecordingStrategy(fixed_signal_factory)
    registry = _FakeRegistry(strategy)
    provider = _FakeProvider(candles)

    from core.confidence.confidence_engine import ConfidenceEngine
    from core.selection.strategy_selection_engine import StrategySelectionEngine

    confidence_engine = ConfidenceEngine(thresholds={"weak_max": 49, "medium_max": 74}, multi_strategy_agreement_bonus=10)
    selection_engine = StrategySelectionEngine(confidence_engine=confidence_engine, filters=[], min_risk_reward=1.0)
    engine = BacktestEngine(provider=provider, registry=registry, selection_engine=selection_engine)
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
