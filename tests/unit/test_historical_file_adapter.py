from pathlib import Path

from adapters.historical_file.file_adapter import HistoricalFileMarketDataProvider
from core.market_data.models import Symbol, Timeframe

SYMBOL = Symbol(name="EURUSD", pip_size=0.0001, digits=5, contract_size=100000)


def test_get_ohlcv_reads_and_sorts_csv(tmp_path: Path):
    csv_path = tmp_path / "EURUSD_M15.csv"
    csv_path.write_text(
        "timestamp,open,high,low,close,volume,spread\n"
        "2026-01-01T00:15:00+00:00,1.1005,1.1010,1.1000,1.1002,120,0.0001\n"
        "2026-01-01T00:00:00+00:00,1.1000,1.1008,1.0995,1.1005,100,0.0001\n"
    )
    provider = HistoricalFileMarketDataProvider(data_dir=tmp_path)

    series = provider.get_ohlcv(SYMBOL, Timeframe.M15, count=10)

    assert len(series) == 2
    assert series.candles[0].timestamp < series.candles[1].timestamp


def test_get_ohlcv_respects_count_limit(tmp_path: Path):
    rows = ["timestamp,open,high,low,close,volume"]
    for i in range(5):
        rows.append(f"2026-01-01T00:{i:02d}:00+00:00,1.1,1.1,1.1,1.1,100")
    (tmp_path / "EURUSD_M1.csv").write_text("\n".join(rows) + "\n")
    provider = HistoricalFileMarketDataProvider(data_dir=tmp_path)

    series = provider.get_ohlcv(SYMBOL, Timeframe.M1, count=3)

    assert len(series) == 3


def test_get_ticks_filters_by_range(tmp_path: Path):
    (tmp_path / "EURUSD_ticks.csv").write_text(
        "timestamp,bid,ask,volume\n"
        "2026-01-01T00:00:00+00:00,1.1000,1.1001,1\n"
        "2026-01-01T00:05:00+00:00,1.1002,1.1003,1\n"
        "2026-01-01T00:10:00+00:00,1.1004,1.1005,1\n"
    )
    provider = HistoricalFileMarketDataProvider(data_dir=tmp_path)
    from datetime import datetime, timezone
    start = datetime(2026, 1, 1, 0, 4, tzinfo=timezone.utc)
    end = datetime(2026, 1, 1, 0, 9, tzinfo=timezone.utc)

    ticks = provider.get_ticks(SYMBOL, start, end)

    assert len(ticks) == 1
    assert ticks[0].bid == 1.1002


def test_is_connected_reflects_data_dir_existence(tmp_path: Path):
    provider = HistoricalFileMarketDataProvider(data_dir=tmp_path / "missing")
    assert provider.is_connected() is False
