from datetime import datetime, timedelta, timezone

from adapters.mock.mock_adapter import MockMarketDataProvider
from core.market_data.models import Timeframe


def test_get_ohlcv_returns_requested_count_in_order():
    provider = MockMarketDataProvider(seed=1)
    symbol = provider.get_symbol_info("EURUSD")

    series = provider.get_ohlcv(symbol, Timeframe.M15, count=50)

    assert len(series) == 50
    timestamps = [c.timestamp for c in series.candles]
    assert timestamps == sorted(timestamps)


def test_get_ticks_stay_within_requested_range():
    provider = MockMarketDataProvider(seed=1)
    symbol = provider.get_symbol_info("EURUSD")
    start = datetime.now(timezone.utc)
    end = start + timedelta(seconds=5)

    ticks = provider.get_ticks(symbol, start, end)

    assert all(start <= t.timestamp <= end for t in ticks)
    assert all(t.ask >= t.bid for t in ticks)


def test_is_connected_always_true_for_mock():
    assert MockMarketDataProvider().is_connected() is True
