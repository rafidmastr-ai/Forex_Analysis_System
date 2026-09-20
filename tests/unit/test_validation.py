from datetime import datetime, timedelta, timezone

import pytest

from adapters.mock.mock_adapter import MockMarketDataProvider
from core.market_data.models import Candle, CandleSeries, Symbol, Timeframe
from core.market_data.provider_interface import MarketDataProvider
from core.market_data.validation import DataQualityError, ValidatingMarketDataProvider


def test_clean_mock_data_passes_validation():
    wrapped = MockMarketDataProvider(seed=7)
    provider = ValidatingMarketDataProvider(wrapped)
    symbol = provider.get_symbol_info("EURUSD")

    series = provider.get_ohlcv(symbol, Timeframe.M15, count=20)

    assert len(series) == 20
    assert not any(issue.startswith("CRITICAL") for issue in provider.last_report.issues)


class _BrokenProvider(MarketDataProvider):
    """Returns a series with high < low to trigger a critical validation failure."""

    def __init__(self, symbol: Symbol, bad_candle: Candle):
        self._symbol = symbol
        self._bad_candle = bad_candle

    def is_connected(self) -> bool:
        return True

    def get_symbol_info(self, symbol_name: str) -> Symbol:
        return self._symbol

    def get_ohlcv(self, symbol, timeframe, count):
        return CandleSeries(symbol=symbol, timeframe=timeframe, candles=[self._bad_candle])

    def get_ticks(self, symbol, start, end):
        return []

    def get_latest_tick(self, symbol):
        raise NotImplementedError


def test_invalid_ohlc_raises_data_quality_error():
    symbol = Symbol(name="EURUSD", pip_size=0.0001, digits=5, contract_size=100000)
    bad_candle = Candle(
        timestamp=datetime.now(timezone.utc), open=1.1000, high=1.0990, low=1.1010,  # high < low
        close=1.1000, volume=100,
    )
    provider = ValidatingMarketDataProvider(_BrokenProvider(symbol, bad_candle))

    with pytest.raises(DataQualityError):
        provider.get_ohlcv(symbol, Timeframe.M15, count=1)


def test_naive_timestamp_is_flagged_as_critical():
    symbol = Symbol(name="EURUSD", pip_size=0.0001, digits=5, contract_size=100000)
    naive_candle = Candle(
        timestamp=datetime.now(),  # no tzinfo — must fail
        open=1.1000, high=1.1010, low=1.0990, close=1.1005, volume=100,
    )
    provider = ValidatingMarketDataProvider(_BrokenProvider(symbol, naive_candle))

    with pytest.raises(DataQualityError):
        provider.get_ohlcv(symbol, Timeframe.M15, count=1)


class _SeriesProvider(MarketDataProvider):
    """Returns a fixed list of candles as-is, for testing multi-candle checks."""

    def __init__(self, symbol: Symbol, candles: list[Candle]):
        self._symbol = symbol
        self._candles = candles

    def is_connected(self) -> bool:
        return True

    def get_symbol_info(self, symbol_name: str) -> Symbol:
        return self._symbol

    def get_ohlcv(self, symbol, timeframe, count):
        return CandleSeries(symbol=symbol, timeframe=timeframe, candles=self._candles)

    def get_ticks(self, symbol, start, end):
        return []

    def get_latest_tick(self, symbol):
        raise NotImplementedError


SYMBOL = Symbol(name="EURUSD", pip_size=0.0001, digits=5, contract_size=100000)


def _candle(minute: int, **overrides) -> Candle:
    base = dict(
        timestamp=datetime(2026, 1, 1, 0, minute, tzinfo=timezone.utc),
        open=1.1000, high=1.1010, low=1.0990, close=1.1005, volume=100,
    )
    base.update(overrides)
    return Candle(**base)


def test_duplicate_timestamps_are_reported_but_not_fatal():
    candles = [_candle(0), _candle(0)]
    provider = ValidatingMarketDataProvider(_SeriesProvider(SYMBOL, candles))

    series = provider.get_ohlcv(SYMBOL, Timeframe.M1, count=2)

    assert len(series) == 2
    assert any("duplicate timestamp" in issue for issue in provider.last_report.issues)


def test_out_of_order_candles_raise_data_quality_error():
    candles = [_candle(5), _candle(1)]
    provider = ValidatingMarketDataProvider(_SeriesProvider(SYMBOL, candles))

    with pytest.raises(DataQualityError):
        provider.get_ohlcv(SYMBOL, Timeframe.M1, count=2)


def test_gap_between_candles_is_detected():
    candles = [_candle(0), _candle(1), _candle(10)]  # M1 timeframe, big jump
    provider = ValidatingMarketDataProvider(_SeriesProvider(SYMBOL, candles))

    series = provider.get_ohlcv(SYMBOL, Timeframe.M1, count=3)

    assert len(series) == 3
    assert len(provider.last_report.gaps) == 1


def test_non_utc_offset_timestamp_is_flagged():
    tz_plus2 = timezone(timedelta(hours=2))
    candles = [_candle(0, timestamp=datetime(2026, 1, 1, 0, 0, tzinfo=tz_plus2))]
    provider = ValidatingMarketDataProvider(_SeriesProvider(SYMBOL, candles))

    series = provider.get_ohlcv(SYMBOL, Timeframe.M1, count=1)

    assert len(series) == 1
    assert any("not normalized to UTC" in issue for issue in provider.last_report.issues)


def test_negative_spread_raises_data_quality_error():
    candles = [_candle(0, spread=-0.0001)]
    provider = ValidatingMarketDataProvider(_SeriesProvider(SYMBOL, candles))

    with pytest.raises(DataQualityError):
        provider.get_ohlcv(SYMBOL, Timeframe.M1, count=1)


def test_spread_above_max_is_reported():
    candles = [_candle(0, spread=0.01)]  # far above EURUSD's typical max
    provider = ValidatingMarketDataProvider(_SeriesProvider(SYMBOL, candles), max_spread_by_symbol={"EURUSD": 0.0005})

    series = provider.get_ohlcv(SYMBOL, Timeframe.M1, count=1)

    assert len(series) == 1
    assert any("exceeds max" in issue for issue in provider.last_report.issues)


def test_max_spread_is_interpreted_in_pips_not_raw_price_units():
    """Regression test: config/settings.*.yaml writes max_spread as pips
    (e.g. EURUSD: 2.0 meaning 2 pips), matching how a trader reads it. A
    3-pip spread (0.0003 for EURUSD, pip_size=0.0001) must be flagged
    against a 2.0-pip limit; a 1-pip spread must not."""
    three_pip_candle = _candle(0, spread=0.0003)
    one_pip_candle = _candle(0, spread=0.0001)

    flagged = ValidatingMarketDataProvider(_SeriesProvider(SYMBOL, [three_pip_candle]), max_spread_by_symbol={"EURUSD": 2.0})
    clean = ValidatingMarketDataProvider(_SeriesProvider(SYMBOL, [one_pip_candle]), max_spread_by_symbol={"EURUSD": 2.0})

    flagged.get_ohlcv(SYMBOL, Timeframe.M1, count=1)
    clean.get_ohlcv(SYMBOL, Timeframe.M1, count=1)

    assert any("exceeds max" in issue for issue in flagged.last_report.issues)
    assert not any("exceeds max" in issue for issue in clean.last_report.issues)


def test_empty_series_is_critical():
    provider = ValidatingMarketDataProvider(_SeriesProvider(SYMBOL, []))

    with pytest.raises(DataQualityError):
        provider.get_ohlcv(SYMBOL, Timeframe.M1, count=0)


def test_tick_ask_below_bid_raises_data_quality_error():
    from core.market_data.models import Tick

    class _BadTickProvider(_SeriesProvider):
        def get_latest_tick(self, symbol):
            return Tick(timestamp=datetime.now(timezone.utc), bid=1.1010, ask=1.1000)

    provider = ValidatingMarketDataProvider(_BadTickProvider(SYMBOL, []))

    with pytest.raises(DataQualityError):
        provider.get_latest_tick(SYMBOL)
