"""Regression tests for scripts/build_m1_historical_data.py: data source
path, symbol coverage, M1->HTF aggregation correctness, incomplete
trailing-candle removal, and fail-loud validation. Uses small synthetic
CSVs (never the real uploaded files) so these run fast and don't depend on
data/market/ existing in every environment.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.build_m1_historical_data import (  # noqa: E402
    MARKET_DATA_DIR,
    SUPPORTED_SYMBOLS,
    _load_m1,
    _manual_groupby_agg,
    _resample_agg,
    build_symbol,
)


def test_data_source_is_data_market_directory_only():
    """The pipeline must read exclusively from data/market/{SYMBOL}.csv --
    never a temporary upload path or any other location."""
    assert MARKET_DATA_DIR == Path("data/market")


def test_supported_symbols_include_all_four():
    assert set(SUPPORTED_SYMBOLS) == {"EURUSD", "XAUUSD", "GBPUSD", "NZDUSD"}


def test_gbpusd_and_nzdusd_are_not_silently_ignored():
    """Both new symbols must be present, not just EURUSD/XAUUSD."""
    assert "GBPUSD" in SUPPORTED_SYMBOLS
    assert "NZDUSD" in SUPPORTED_SYMBOLS


def _write_csv(path: Path, rows: list[dict], timestamp_col: str = "timestamp") -> None:
    pd.DataFrame(rows).to_csv(path, index=False)


def _epoch_ms_rows(n: int, start_ms: int = 1_756_684_800_000, step_ms: int = 60_000) -> list[dict]:
    rows = []
    price = 1.1000
    for i in range(n):
        price += 0.0001
        rows.append({
            "timestamp": start_ms + i * step_ms,
            "open": round(price, 5), "high": round(price + 0.0003, 5),
            "low": round(price - 0.0003, 5), "close": round(price + 0.0001, 5),
        })
    return rows


def test_load_m1_accepts_epoch_ms_timestamp_format(tmp_path):
    path = tmp_path / "EURUSD.csv"
    _write_csv(path, _epoch_ms_rows(10))
    df = _load_m1(path)
    assert len(df) == 10
    assert df["dt"].is_monotonic_increasing


def test_load_m1_accepts_datetime_text_format(tmp_path):
    path = tmp_path / "GBPUSD.csv"
    rows = [
        {"datetime": "2025-09-01 00:00:00", "open": 1.35, "high": 1.351, "low": 1.349, "close": 1.3505},
        {"datetime": "2025-09-01 00:01:00", "open": 1.3505, "high": 1.352, "low": 1.350, "close": 1.3510},
    ]
    _write_csv(path, rows)
    df = _load_m1(path)
    assert len(df) == 2


def test_load_m1_rejects_missing_ohlc_column(tmp_path):
    path = tmp_path / "bad.csv"
    pd.DataFrame([{"timestamp": 1_756_684_800_000, "open": 1.1, "high": 1.2, "low": 1.0}]).to_csv(path, index=False)
    with pytest.raises(ValueError, match="missing required column"):
        _load_m1(path)


def test_load_m1_rejects_no_recognized_timestamp_column(tmp_path):
    path = tmp_path / "bad.csv"
    pd.DataFrame([{"time": 1, "open": 1.1, "high": 1.2, "low": 1.0, "close": 1.1}]).to_csv(path, index=False)
    with pytest.raises(ValueError, match="no recognized timestamp column"):
        _load_m1(path)


def test_load_m1_rejects_duplicate_timestamps(tmp_path):
    path = tmp_path / "dup.csv"
    rows = _epoch_ms_rows(5)
    rows.append(dict(rows[0]))  # exact duplicate timestamp
    _write_csv(path, rows)
    with pytest.raises(ValueError, match="duplicate timestamp"):
        _load_m1(path)


def test_load_m1_rejects_nan_ohlc(tmp_path):
    path = tmp_path / "nan.csv"
    rows = _epoch_ms_rows(3)
    rows[1]["close"] = float("nan")
    _write_csv(path, rows)
    with pytest.raises(ValueError, match="NaN"):
        _load_m1(path)


def test_load_m1_rejects_high_below_max_open_close(tmp_path):
    path = tmp_path / "invalid_high.csv"
    rows = _epoch_ms_rows(3)
    rows[1]["high"] = rows[1]["open"] - 0.01  # high below open -- impossible
    _write_csv(path, rows)
    with pytest.raises(ValueError, match="high < max"):
        _load_m1(path)


def test_load_m1_rejects_low_above_min_open_close(tmp_path):
    path = tmp_path / "invalid_low.csv"
    rows = _epoch_ms_rows(3)
    # Between open and close (so it does NOT also violate high >= max(...)),
    # but still above min(open, close) -- violates ONLY the low check.
    rows[1]["low"] = rows[1]["open"] + 0.00005
    _write_csv(path, rows)
    with pytest.raises(ValueError, match="low > min"):
        _load_m1(path)


def test_load_m1_rejects_zero_or_negative_price(tmp_path):
    path = tmp_path / "zero.csv"
    rows = _epoch_ms_rows(3)
    rows[1]["close"] = 0.0
    _write_csv(path, rows)
    with pytest.raises(ValueError, match="zero/negative"):
        _load_m1(path)


def test_load_m1_sorts_out_of_order_rows(tmp_path):
    path = tmp_path / "unsorted.csv"
    rows = _epoch_ms_rows(5)
    rows.reverse()
    _write_csv(path, rows)
    df = _load_m1(path)
    assert df["dt"].is_monotonic_increasing


def test_m1_to_m5_aggregation_is_correct(tmp_path):
    path = tmp_path / "EURUSD.csv"
    _write_csv(path, _epoch_ms_rows(15))  # exactly 3 full M5 buckets
    df = _load_m1(path)
    agg = _manual_groupby_agg(df, "5min")
    assert len(agg) == 3
    for i, row in agg.iterrows():
        bucket_rows = df.iloc[i * 5:(i + 1) * 5]
        assert row["open"] == pytest.approx(bucket_rows["open"].iloc[0])
        assert row["high"] == pytest.approx(bucket_rows["high"].max())
        assert row["low"] == pytest.approx(bucket_rows["low"].min())
        assert row["close"] == pytest.approx(bucket_rows["close"].iloc[-1])
        assert row["n_bars"] == 5


def test_m1_to_m15_aggregation_is_correct(tmp_path):
    path = tmp_path / "EURUSD.csv"
    _write_csv(path, _epoch_ms_rows(30))  # exactly 2 full M15 buckets
    df = _load_m1(path)
    agg = _manual_groupby_agg(df, "15min")
    assert len(agg) == 2
    for i, row in agg.iterrows():
        bucket_rows = df.iloc[i * 15:(i + 1) * 15]
        assert row["open"] == pytest.approx(bucket_rows["open"].iloc[0])
        assert row["high"] == pytest.approx(bucket_rows["high"].max())
        assert row["low"] == pytest.approx(bucket_rows["low"].min())
        assert row["close"] == pytest.approx(bucket_rows["close"].iloc[-1])
        assert row["n_bars"] == 15


def test_m1_to_h1_aggregation_is_correct(tmp_path):
    path = tmp_path / "EURUSD.csv"
    _write_csv(path, _epoch_ms_rows(120))  # exactly 2 full H1 buckets
    df = _load_m1(path)
    agg = _manual_groupby_agg(df, "1h")
    assert len(agg) == 2
    for i, row in agg.iterrows():
        bucket_rows = df.iloc[i * 60:(i + 1) * 60]
        assert row["open"] == pytest.approx(bucket_rows["open"].iloc[0])
        assert row["high"] == pytest.approx(bucket_rows["high"].max())
        assert row["low"] == pytest.approx(bucket_rows["low"].min())
        assert row["close"] == pytest.approx(bucket_rows["close"].iloc[-1])
        assert row["n_bars"] == 60


def test_resample_and_manual_aggregation_agree_on_a_realistic_series(tmp_path):
    path = tmp_path / "EURUSD.csv"
    _write_csv(path, _epoch_ms_rows(500))
    df = _load_m1(path)
    for rule in ("5min", "15min", "1h", "4h"):
        resampled = _resample_agg(df, rule)
        manual = _manual_groupby_agg(df, rule)
        merged = resampled.merge(manual, on="dt", suffixes=("_r", "_m"))
        assert len(merged) == len(resampled) == len(manual)
        for col in ("open", "high", "low", "close"):
            assert (merged[f"{col}_r"] - merged[f"{col}_m"]).abs().max() < 1e-9


def test_build_symbol_drops_incomplete_trailing_candle(tmp_path):
    """A final partial H1 bucket (fewer than 60 M1 bars, at the very end of
    the data) must be dropped -- it has not actually closed yet from the
    perspective of this dataset's own history."""
    rows = _epoch_ms_rows(65)  # one full H1 bucket (60) + a 5-bar partial tail
    path = tmp_path / "EURUSD.csv"
    _write_csv(path, rows)
    df = _load_m1(path)
    manual = _manual_groupby_agg(df, "1h")
    assert len(manual) == 2  # both resample()/groupby() include the partial bucket raw...
    last_bucket_end = manual["dt"].iloc[-1] + pd.Timedelta(minutes=60)
    data_end = df["dt"].iloc[-1] + pd.Timedelta(minutes=1)
    assert last_bucket_end > data_end  # ... confirming it IS incomplete and must be trimmed by build_symbol

    out_dir = tmp_path / "historical"
    import scripts.build_m1_historical_data as mod
    old_output_dir = mod.OUTPUT_DIR
    mod.OUTPUT_DIR = out_dir
    try:
        report = build_symbol("EURUSD", path)
    finally:
        mod.OUTPUT_DIR = old_output_dir

    assert report["timeframes"]["H1"]["n_buckets"] == 1  # the incomplete trailing bucket was dropped
    written = pd.read_csv(out_dir / "EURUSD_H1.csv")
    assert len(written) == 1


def test_build_symbol_writes_volume_zero_and_no_spread_column(tmp_path):
    rows = _epoch_ms_rows(10)
    path = tmp_path / "EURUSD.csv"
    _write_csv(path, rows)

    out_dir = tmp_path / "historical"
    import scripts.build_m1_historical_data as mod
    old_output_dir = mod.OUTPUT_DIR
    mod.OUTPUT_DIR = out_dir
    try:
        build_symbol("EURUSD", path)
    finally:
        mod.OUTPUT_DIR = old_output_dir

    written = pd.read_csv(out_dir / "EURUSD_M1.csv")
    assert (written["volume"] == 0.0).all()
    assert "spread" not in written.columns
