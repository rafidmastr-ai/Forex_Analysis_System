"""MockMarketDataProvider — synthetic data source for Linux Cloud development.

Generates a deterministic random-walk price series so the whole Core
Analysis Engine, Backend API and Web Interface can be built and tested
without any MT5 dependency. Implements MarketDataProvider exactly like any
real adapter would.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from core.market_data.models import Candle, CandleSeries, Symbol, Tick, Timeframe
from core.market_data.provider_interface import MarketDataProvider

_DEFAULT_SYMBOLS = {
    "EURUSD": Symbol(name="EURUSD", pip_size=0.0001, digits=5, contract_size=100000),
    "GBPUSD": Symbol(name="GBPUSD", pip_size=0.0001, digits=5, contract_size=100000),
    "XAUUSD": Symbol(name="XAUUSD", pip_size=0.01, digits=2, contract_size=100),
}


class MockMarketDataProvider(MarketDataProvider):
    def __init__(self, seed: int = 42, base_prices: dict[str, float] | None = None):
        self._rng = random.Random(seed)
        self._base_prices = base_prices or {"EURUSD": 1.0850, "GBPUSD": 1.2650, "XAUUSD": 2350.0}

    def is_connected(self) -> bool:
        return True

    def get_symbol_info(self, symbol_name: str) -> Symbol:
        try:
            return _DEFAULT_SYMBOLS[symbol_name]
        except KeyError as exc:
            raise ValueError(f"unknown mock symbol: {symbol_name}") from exc

    def get_ohlcv(self, symbol: Symbol, timeframe: Timeframe, count: int) -> CandleSeries:
        step = timedelta(minutes=timeframe.minutes)
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        price = self._base_prices.get(symbol.name, 1.0)
        pip = symbol.pip_size
        candles: list[Candle] = []
        start = now - step * count
        for i in range(count):
            ts = start + step * i
            drift = self._rng.uniform(-5, 5) * pip
            open_ = price
            close = price + drift
            high = max(open_, close) + self._rng.uniform(0, 3) * pip
            low = min(open_, close) - self._rng.uniform(0, 3) * pip
            spread = self._rng.uniform(0.5, 1.5) * pip
            candles.append(Candle(timestamp=ts, open=open_, high=high, low=low, close=close,
                                   volume=self._rng.uniform(50, 500), spread=spread))
            price = close
        self._base_prices[symbol.name] = price
        return CandleSeries(symbol=symbol, timeframe=timeframe, candles=candles)

    def get_ticks(self, symbol: Symbol, start: datetime, end: datetime) -> list[Tick]:
        pip = symbol.pip_size
        price = self._base_prices.get(symbol.name, 1.0)
        ticks: list[Tick] = []
        ts = start
        while ts <= end:
            drift = self._rng.uniform(-1, 1) * pip
            bid = price + drift
            ask = bid + self._rng.uniform(0.5, 1.5) * pip
            ticks.append(Tick(timestamp=ts, bid=bid, ask=ask, volume=self._rng.uniform(1, 20)))
            price = bid
            ts += timedelta(seconds=1)
        return ticks

    def get_latest_tick(self, symbol: Symbol) -> Tick:
        pip = symbol.pip_size
        price = self._base_prices.get(symbol.name, 1.0)
        bid = price + self._rng.uniform(-1, 1) * pip
        ask = bid + self._rng.uniform(0.5, 1.5) * pip
        return Tick(timestamp=datetime.now(timezone.utc), bid=bid, ask=ask, volume=self._rng.uniform(1, 20))
