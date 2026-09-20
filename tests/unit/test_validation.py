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
