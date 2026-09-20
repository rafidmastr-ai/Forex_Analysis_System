"""Market data domain models.

Pure data structures with zero knowledge of any data source. Nothing in
this module may import MetaTrader5 or any adapter — Candle/Tick/CandleSeries
are the common currency the whole system speaks.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Timeframe(str, Enum):
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"

    @property
    def minutes(self) -> int:
        return {
            Timeframe.M1: 1,
            Timeframe.M5: 5,
            Timeframe.M15: 15,
            Timeframe.M30: 30,
            Timeframe.H1: 60,
            Timeframe.H4: 240,
            Timeframe.D1: 1440,
        }[self]


@dataclass(frozen=True)
class Symbol:
    name: str
    pip_size: float
    digits: int
    contract_size: float
    # Full broker specification. Optional so hand-built Symbols (mock data,
    # tests, config defaults) keep working; adapters that have real specs
    # (MT5) should always populate these rather than leaving them None.
    tick_size: float | None = None
    tick_value: float | None = None
    volume_min: float | None = None
    volume_max: float | None = None
    volume_step: float | None = None
    point: float | None = None


@dataclass(frozen=True)
class Candle:
    timestamp: datetime  # UTC, bar open time
    open: float
    high: float
    low: float
    close: float
    volume: float
    spread: float | None = None


@dataclass
class CandleSeries:
    symbol: Symbol
    timeframe: Timeframe
    candles: list[Candle] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.candles)

    def is_empty(self) -> bool:
        return len(self.candles) == 0

    def last(self) -> Candle | None:
        return self.candles[-1] if self.candles else None

    def sliced_as_of(self, as_of: datetime) -> "CandleSeries":
        """Return only candles fully closed at or before `as_of`.

        This is the single mechanism the whole system uses to avoid
        look-ahead: nothing downstream should ever slice `.candles` by
        hand. `candles` is always chronologically ordered (enforced by the
        Data Validation Layer), so this is a binary search — important for
        the Backtesting Engine, which calls this once per simulated bar;
        a linear scan here would make a full backtest run O(n^2).
        """
        idx = bisect_right(self.candles, as_of, key=lambda c: c.timestamp)
        return CandleSeries(symbol=self.symbol, timeframe=self.timeframe, candles=self.candles[:idx])


@dataclass(frozen=True)
class Tick:
    timestamp: datetime  # UTC
    bid: float
    ask: float
    volume: float = 0.0

    @property
    def spread(self) -> float:
        return self.ask - self.bid
