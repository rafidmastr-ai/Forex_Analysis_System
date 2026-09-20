"""MarketDataProvider — the one contract every data source must implement.

Core code depends only on this interface, never on a concrete adapter.
Swapping MT5 for another broker/data vendor means writing a new class that
implements this interface — nothing above this line changes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from core.market_data.models import CandleSeries, Symbol, Tick, Timeframe


class MarketDataProvider(ABC):
    @abstractmethod
    def get_ohlcv(self, symbol: Symbol, timeframe: Timeframe, count: int) -> CandleSeries:
        """Return the most recent `count` closed candles."""

    @abstractmethod
    def get_ticks(self, symbol: Symbol, start: datetime, end: datetime) -> list[Tick]:
        """Return historical tick data in [start, end]."""

    @abstractmethod
    def get_latest_tick(self, symbol: Symbol) -> Tick:
        """Return the current bid/ask snapshot."""

    @abstractmethod
    def get_symbol_info(self, symbol_name: str) -> Symbol:
        """Resolve a symbol name to its trading specification."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Whether this provider currently has a usable data connection."""
