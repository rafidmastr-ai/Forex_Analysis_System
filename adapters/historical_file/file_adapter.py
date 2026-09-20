"""HistoricalFileMarketDataProvider — reads previously exported CSV data.

Used by the Backtesting Engine (and by Cloud development when a realistic,
non-random dataset is wanted). Expected CSV columns:
    timestamp,open,high,low,close,volume[,spread]
`timestamp` must be ISO-8601 UTC.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from core.market_data.models import Candle, CandleSeries, Symbol, Tick, Timeframe
from core.market_data.provider_interface import MarketDataProvider


class HistoricalFileMarketDataProvider(MarketDataProvider):
    def __init__(self, data_dir: Path | str, symbols: dict[str, Symbol] | None = None):
        self._data_dir = Path(data_dir)
        # CSV files carry no symbol specification (contract size, digits...),
        # so the caller must supply it. `symbols` maps NAME -> Symbol; without
        # an entry for a requested name, get_symbol_info fails loudly instead
        # of guessing at broker-specific specs.
        self._symbols = symbols or {}

    def is_connected(self) -> bool:
        return self._data_dir.exists()

    def get_symbol_info(self, symbol_name: str) -> Symbol:
        try:
            return self._symbols[symbol_name]
        except KeyError as exc:
            raise ValueError(
                f"no symbol spec supplied for {symbol_name!r} — pass it in "
                "HistoricalFileMarketDataProvider(symbols={...}) at construction"
            ) from exc

    def get_ohlcv(self, symbol: Symbol, timeframe: Timeframe, count: int) -> CandleSeries:
        path = self._csv_path(symbol.name, timeframe)
        candles: list[Candle] = []
        with path.open(newline="") as f:
            for row in csv.DictReader(f):
                candles.append(
                    Candle(
                        timestamp=datetime.fromisoformat(row["timestamp"]).astimezone(timezone.utc),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row["volume"]),
                        spread=float(row["spread"]) if row.get("spread") else None,
                    )
                )
        candles.sort(key=lambda c: c.timestamp)
        return CandleSeries(symbol=symbol, timeframe=timeframe, candles=candles[-count:])

    def get_ticks(self, symbol: Symbol, start: datetime, end: datetime) -> list[Tick]:
        path = self._data_dir / f"{symbol.name}_ticks.csv"
        if not path.exists():
            return []
        ticks: list[Tick] = []
        with path.open(newline="") as f:
            for row in csv.DictReader(f):
                ts = datetime.fromisoformat(row["timestamp"]).astimezone(timezone.utc)
                if start <= ts <= end:
                    ticks.append(Tick(timestamp=ts, bid=float(row["bid"]), ask=float(row["ask"]),
                                       volume=float(row.get("volume", 0))))
        return ticks

    def get_latest_tick(self, symbol: Symbol) -> Tick:
        raise NotImplementedError("HistoricalFileMarketDataProvider has no notion of 'latest' — use get_ticks.")

    def _csv_path(self, symbol_name: str, timeframe: Timeframe) -> Path:
        return self._data_dir / f"{symbol_name}_{timeframe.value}.csv"
