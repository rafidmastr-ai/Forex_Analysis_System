#!/usr/bin/env python3
"""Convert a raw MT5 terminal CSV export into the format
HistoricalFileMarketDataProvider expects (timestamp,open,high,low,close,
volume,spread — ISO-8601 UTC timestamps).

MT5's own "Export bars" produces tab-separated files shaped like:
    <DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>
    2025.09.15\t00:00:00\t1.17269\t1.17350\t1.17269\t1.17315\t119\t0\t8
with SPREAD in raw broker points and VOL almost always 0 for forex (no
real volume feed) — TICKVOL is used as the volume proxy instead.

IMPORTANT — timezone caveat (read before trusting time-of-day-sensitive
results): MT5 exports carry no timezone. This script tags them UTC purely
so the Data Validation Layer accepts them (it requires timezone-aware
UTC), NOT because the broker's server clock has been confirmed to be UTC.
Evidence in this dataset (week boundaries fall exactly Monday 00:00 ->
Friday 23:45 in the exported clock, whereas the real forex week opens
Sunday ~21-22:00 UTC) suggests the export is in a broker server time
offset from UTC by a few hours — common for MT5 brokers, but the exact
offset cannot be determined from the file alone. Anything derived from
absolute time-of-day — most importantly the ICT strategy's Kill Zones,
which are defined in true New York time — will be shifted by that same
unknown offset when backtesting on this data. This does NOT affect
Point-in-Time correctness (no look-ahead), only which kill zone a given
bar appears to fall in.

Usage:
    python3 scripts/convert_mt5_export.py <input_dir> <output_dir>
"""
from __future__ import annotations

import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

# Standard specs for the symbols this dataset covers. Point/digits observed
# directly from the exported price precision (EURUSD: 5 decimals -> point
# 0.00001; XAUUSD: 2 decimals -> point 0.01) since no live MT5 connection is
# available to query symbol_info() in this environment.
POINT_BY_SYMBOL = {
    "EURUSD": 0.00001,
    "XAUUSD": 0.01,
}


def convert_file(src: Path, dst_dir: Path) -> Path:
    symbol, timeframe = _parse_symbol_and_timeframe(src.name)
    point = POINT_BY_SYMBOL.get(symbol)
    if point is None:
        raise ValueError(f"no known point size for symbol {symbol!r} — add it to POINT_BY_SYMBOL")

    dst = dst_dir / f"{symbol}_{timeframe}.csv"
    with src.open(newline="") as f_in, dst.open("w", newline="") as f_out:
        reader = csv.DictReader(f_in, delimiter="\t")
        writer = csv.writer(f_out)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume", "spread"])
        for row in reader:
            row = {k.strip("<>"): v for k, v in row.items()}
            ts = datetime.strptime(f"{row['DATE']} {row['TIME']}", "%Y.%m.%d %H:%M:%S")
            ts = ts.replace(tzinfo=timezone.utc)  # see the timezone caveat in the module docstring
            spread_price = float(row["SPREAD"]) * point
            writer.writerow([
                ts.isoformat(), row["OPEN"], row["HIGH"], row["LOW"], row["CLOSE"],
                row["TICKVOL"], f"{spread_price:.10f}",
            ])
    return dst


def _parse_symbol_and_timeframe(filename: str) -> tuple[str, str]:
    # e.g. "EURUSD_M15_202509150000_202609160000.csv" -> ("EURUSD", "M15")
    stem = filename.removesuffix(".csv")
    parts = stem.split("_")
    if len(parts) < 2:
        raise ValueError(f"cannot parse symbol/timeframe from filename: {filename!r}")
    return parts[0], parts[1]


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 1
    input_dir, output_dir = Path(argv[1]), Path(argv[2])
    output_dir.mkdir(parents=True, exist_ok=True)

    converted = []
    for src in sorted(input_dir.glob("*.csv")):
        dst = convert_file(src, output_dir)
        converted.append(dst)
        print(f"{src.name} -> {dst}")

    print(f"\nConverted {len(converted)} file(s) into {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
