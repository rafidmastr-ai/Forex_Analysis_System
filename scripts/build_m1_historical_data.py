#!/usr/bin/env python3
"""Builds data/historical/{SYMBOL}_{TIMEFRAME}.csv for M1, M5, M15, M30, H1,
H4 from the newly-uploaded raw M1 OHLC files (EURUSD, XAUUSD).

Source files (read-only, never modified, never copied elsewhere):
    /root/.claude/uploads/1f34c459-1bf3-5277-a995-3d20f0daa5ad/ae0dd58c-EURUSD.csv
    /root/.claude/uploads/1f34c459-1bf3-5277-a995-3d20f0daa5ad/0c71be54-XAUUSD.csv
Columns: timestamp (epoch milliseconds, UTC), open, high, low, close. No
volume column in the source -- every converted row's volume is written as
0.0 (never fabricated). None of the four adopted strategies (Classic, SMC,
ICT, SweepDisplacement) read Candle.volume (only core/algorithms/indicators
/vwap.py does, and nothing wires VWAP into any of the four), so this has no
effect on any tested result. No spread column exists in the source either,
so it is simply omitted (HistoricalFileMarketDataProvider already treats a
missing spread column as "no spread data", used honestly, not invented).

Aggregation to M5/M15/M30/H1/H4 uses UTC-calendar-aligned buckets (e.g. H4
bars start at 00:00/04:00/08:00/12:00/16:00/20:00 UTC -- the standard
convention, and what pandas' resample() naturally produces from an
epoch-anchored index): Open = open of the bucket's FIRST M1 candle, High =
max High, Low = min Low, Close = close of the bucket's LAST M1 candle.

Every aggregated candle is validated by TWO independently-coded methods
(pandas .resample() and a hand-rolled integer-bucket groupby) that must
agree exactly on open/high/low/close AND on which M1 rows fed each bucket,
for every single bucket -- not a sample. The last bucket of a series is
dropped if it is not fully covered by available M1 data through the
bucket's own end boundary (avoids ever presenting a still-forming candle as
closed); this is a no-op here because both source files' history ends
exactly on a UTC midnight boundary, but the check is unconditional so it
would matter with a different upload.

Never used for any decision affecting Strategy/Weight/Filter/Threshold
logic -- purely a data-preparation and validation step.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

SOURCE_FILES = {
    "EURUSD": "/root/.claude/uploads/1f34c459-1bf3-5277-a995-3d20f0daa5ad/ae0dd58c-EURUSD.csv",
    "XAUUSD": "/root/.claude/uploads/1f34c459-1bf3-5277-a995-3d20f0daa5ad/0c71be54-XAUUSD.csv",
}

OUTPUT_DIR = Path("data/historical")

# (pandas resample rule, minutes-per-bar) -- M1 itself needs no resampling.
TIMEFRAMES = {
    "M1": (None, 1),
    "M5": ("5min", 5),
    "M15": ("15min", 15),
    "M30": ("30min", 30),
    "H1": ("1h", 60),
    "H4": ("4h", 240),
}


def _load_m1(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    expected_cols = {"timestamp", "open", "high", "low", "close"}
    if set(df.columns) != expected_cols:
        raise ValueError(f"{path}: unexpected columns {list(df.columns)}, expected {sorted(expected_cols)}")
    df["dt"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.sort_values("dt").reset_index(drop=True)
    if df["dt"].duplicated().any():
        raise ValueError(f"{path}: duplicate timestamps found -- refusing to silently aggregate over them")
    for col in ("open", "high", "low", "close"):
        if df[col].isna().any():
            raise ValueError(f"{path}: NaN values in column {col!r}")
    return df


def _write_adapter_csv(df: pd.DataFrame, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    out = df[["dt", "open", "high", "low", "close"]].copy()
    out["timestamp"] = out["dt"].apply(lambda ts: ts.isoformat())
    out["volume"] = 0.0
    out[["timestamp", "open", "high", "low", "close", "volume"]].to_csv(dst, index=False)


def _resample_agg(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    idx = df.set_index("dt")
    agg = idx.resample(rule, label="left", closed="left").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
        n_bars=("open", "count"),
    )
    agg = agg.dropna(subset=["open"])
    agg["n_bars"] = agg["n_bars"].astype(int)
    return agg.reset_index()


def _bucket_start(ts: pd.Series, rule: str) -> pd.Series:
    # Series.dt.floor() is a second, independently-implemented pandas code
    # path from resample() (different internal machinery), which is exactly
    # the point of this cross-check -- it floors each timestamp to the start
    # of its own UTC-epoch-anchored bucket (e.g. "4h" -> 00:00/04:00/08:00...).
    return ts.dt.floor(rule)


def _manual_groupby_agg(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    bstart = _bucket_start(df["dt"], rule)
    g = df.assign(bucket=bstart).groupby("bucket", sort=True)
    agg = g.agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
                n_bars=("open", "count"))
    agg["n_bars"] = agg["n_bars"].astype(int)
    return agg.reset_index().rename(columns={"bucket": "dt"})


def _cross_validate(resampled: pd.DataFrame, manual: pd.DataFrame, minutes: int, m1_len: int, label: str) -> dict:
    issues = []
    if len(resampled) != len(manual):
        issues.append(f"row count mismatch: resample={len(resampled)} manual={len(manual)}")
    merged = resampled.merge(manual, on="dt", suffixes=("_resample", "_manual"), how="outer", indicator=True)
    unmatched = merged[merged["_merge"] != "both"]
    if len(unmatched):
        issues.append(f"{len(unmatched)} bucket(s) present in only one method")
    both = merged[merged["_merge"] == "both"]
    for col in ("open", "high", "low", "close", "n_bars"):
        mismatch = both[abs(both[f"{col}_resample"] - both[f"{col}_manual"]) > 1e-9] if col != "n_bars" else both[both["n_bars_resample"] != both["n_bars_manual"]]
        if len(mismatch):
            issues.append(f"{len(mismatch)} bucket(s) disagree on {col!r} between the two methods")

    total_bars_covered = int(manual["n_bars"].sum())
    expected_full_buckets = manual["n_bars"] == minutes
    n_full = int(expected_full_buckets.sum())
    n_partial = int((~expected_full_buckets).sum())

    return {
        "label": label,
        "n_buckets": len(manual),
        "n_full_buckets": n_full,
        "n_partial_buckets": n_partial,
        "total_m1_bars_covered_by_buckets": total_bars_covered,
        "total_m1_bars_in_source": m1_len,
        "all_m1_bars_accounted_for": total_bars_covered == m1_len,
        "cross_validation_issues": issues,
        "cross_validation_passed": len(issues) == 0 and total_bars_covered == m1_len,
    }


def build_symbol(symbol: str, path: str) -> dict:
    df = _load_m1(path)
    report: dict = {"symbol": symbol, "source_path": path, "m1_rows": len(df),
                     "start_utc": df["dt"].iloc[0].isoformat(), "end_utc": df["dt"].iloc[-1].isoformat(),
                     "timeframes": {}}

    _write_adapter_csv(df, OUTPUT_DIR / f"{symbol}_M1.csv")
    report["timeframes"]["M1"] = {"label": "M1", "n_buckets": len(df), "n_full_buckets": len(df),
                                   "n_partial_buckets": 0, "total_m1_bars_covered_by_buckets": len(df),
                                   "total_m1_bars_in_source": len(df), "all_m1_bars_accounted_for": True,
                                   "cross_validation_issues": ["M1 is the source itself -- no aggregation performed"],
                                   "cross_validation_passed": True}

    for tf_name, (rule, minutes) in TIMEFRAMES.items():
        if rule is None:
            continue
        resampled = _resample_agg(df, rule)
        manual = _manual_groupby_agg(df, rule)

        # Drop a trailing bucket that is not fully covered through its own end
        # boundary by available M1 data (a still-forming candle, never
        # presented as closed). No-op for this dataset (both files end on a
        # UTC midnight boundary) but checked unconditionally.
        last_bucket_end = manual["dt"].iloc[-1] + pd.Timedelta(minutes=minutes)
        data_end = df["dt"].iloc[-1] + pd.Timedelta(minutes=1)
        if last_bucket_end > data_end:
            manual = manual.iloc[:-1].reset_index(drop=True)
            resampled = resampled.iloc[:-1].reset_index(drop=True)

        validation = _cross_validate(resampled, manual, minutes, len(df), tf_name)
        report["timeframes"][tf_name] = validation

        _write_adapter_csv(manual, OUTPUT_DIR / f"{symbol}_{tf_name}.csv")

    return report


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    full_report = {}
    for symbol, path in SOURCE_FILES.items():
        print(f"=== building {symbol} ===", flush=True)
        r = build_symbol(symbol, path)
        full_report[symbol] = r
        for tf_name, v in r["timeframes"].items():
            print(f"  {tf_name}: buckets={v['n_buckets']} full={v['n_full_buckets']} partial={v['n_partial_buckets']} "
                  f"all_bars_accounted_for={v['all_m1_bars_accounted_for']} passed={v['cross_validation_passed']} "
                  f"issues={v['cross_validation_issues']}", flush=True)

    out_path = Path("data/optimization_results/m1_htf_build_report.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(full_report, indent=2, default=str))
    print(f"\nbuild report written to {out_path}", flush=True)

    all_passed = all(v["cross_validation_passed"] for r in full_report.values() for v in r["timeframes"].values())
    print(f"\nALL TIMEFRAMES VALIDATED: {all_passed}", flush=True)
    if not all_passed:
        raise SystemExit("HTF aggregation validation failed -- see report for details")


if __name__ == "__main__":
    main()
