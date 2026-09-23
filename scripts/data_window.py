"""Single authoritative source for each symbol's available backtest data
window. Never hard-code a start/end date for a symbol anywhere else --
read it from here, which in turn reads it from
scripts/build_m1_historical_data.py's own build report (itself derived
directly from the uploaded CSVs under data/market/, not typed by hand).

Different symbols can (and, in this dataset, do) have slightly different
actual coverage -- e.g. one symbol's raw upload ending a day earlier than
another's. Nothing in this module assumes they are identical; callers get
each symbol's own real range and must not silently substitute another
symbol's window.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

BUILD_REPORT_PATH = Path("data/optimization_results/m1_htf_build_report.json")


def load_data_windows() -> dict[str, tuple[datetime, datetime]]:
    """Every symbol's actual (start, end) as detected by the last run of
    scripts/build_m1_historical_data.py."""
    if not BUILD_REPORT_PATH.exists():
        raise FileNotFoundError(
            f"{BUILD_REPORT_PATH} not found -- run `python scripts/build_m1_historical_data.py` "
            "first so the actual per-symbol data window can be detected before any backtest runs."
        )
    report = json.loads(BUILD_REPORT_PATH.read_text())
    windows: dict[str, tuple[datetime, datetime]] = {}
    for symbol, info in report.items():
        windows[symbol] = (datetime.fromisoformat(info["start_utc"]), datetime.fromisoformat(info["end_utc"]))
    return windows


def full_window_for(symbol_name: str) -> tuple[datetime, datetime]:
    """The one symbol's own actual (start, end) -- never another symbol's,
    never a value typed into a script by hand."""
    windows = load_data_windows()
    if symbol_name not in windows:
        raise KeyError(
            f"no detected data window for symbol {symbol_name!r} -- available: {sorted(windows)}. "
            f"Check that data/market/{symbol_name}.csv exists and was included in the last build."
        )
    return windows[symbol_name]
