"""MT5DataMarketDataProvider — the ONLY module allowed to import MetaTrader5.

Runs exclusively on Windows with a running MT5 Terminal. On any other
platform, importing MetaTrader5 fails — that import is deferred into
`connect()` so this module can still be imported (e.g. by tooling) on
Linux without crashing; it simply cannot be used there.

Credentials are read from environment variables only, never from a config
file that could be committed to git:
    MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, MT5_TERMINAL_PATH (optional)
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from core.market_data.models import Candle, CandleSeries, Symbol, Tick, Timeframe
from core.market_data.provider_interface import MarketDataProvider
from core.risk.account_state import AccountState

_TIMEFRAME_MAP_NAMES = {
    Timeframe.M1: "TIMEFRAME_M1",
    Timeframe.M5: "TIMEFRAME_M5",
    Timeframe.M15: "TIMEFRAME_M15",
    Timeframe.M30: "TIMEFRAME_M30",
    Timeframe.H1: "TIMEFRAME_H1",
    Timeframe.H4: "TIMEFRAME_H4",
    Timeframe.D1: "TIMEFRAME_D1",
}


class MT5ConnectionError(Exception):
    pass


class MT5DataMarketDataProvider(MarketDataProvider):
    def __init__(self):
        self._mt5 = None  # bound to the MetaTrader5 module once connected

    def connect(self) -> None:
        try:
            import MetaTrader5 as mt5  # noqa: N813 — matches the package's own convention
        except ImportError as exc:
            raise MT5ConnectionError(
                "MetaTrader5 package is not available. This adapter only runs on Windows "
                "with the MT5 terminal and package installed."
            ) from exc

        login = os.environ.get("MT5_LOGIN")
        password = os.environ.get("MT5_PASSWORD")
        server = os.environ.get("MT5_SERVER")
        terminal_path = os.environ.get("MT5_TERMINAL_PATH")

        if login is None or password is None or server is None:
            raise MT5ConnectionError(
                "MT5_LOGIN, MT5_PASSWORD and MT5_SERVER must be set as environment variables."
            )

        initialized = mt5.initialize(path=terminal_path) if terminal_path else mt5.initialize()
        if not initialized:
            raise MT5ConnectionError(f"mt5.initialize() failed: {mt5.last_error()}")

        if not mt5.login(int(login), password=password, server=server):
            raise MT5ConnectionError(f"mt5.login() failed: {mt5.last_error()}")

        self._mt5 = mt5

    def is_connected(self) -> bool:
        return self._mt5 is not None and self._mt5.terminal_info() is not None

    def get_symbol_info(self, symbol_name: str) -> Symbol:
        info = self._require_mt5().symbol_info(symbol_name)
        if info is None:
            raise ValueError(f"symbol not found in MT5: {symbol_name}")
        # Real broker specs, never hardcoded, whenever MT5 data is available.
        return Symbol(
            name=symbol_name,
            pip_size=info.point,
            digits=info.digits,
            contract_size=info.trade_contract_size,
            tick_size=info.trade_tick_size,
            tick_value=info.trade_tick_value,
            volume_min=info.volume_min,
            volume_max=info.volume_max,
            volume_step=info.volume_step,
            point=info.point,
        )

    def get_ohlcv(self, symbol: Symbol, timeframe: Timeframe, count: int) -> CandleSeries:
        mt5 = self._require_mt5()
        mt5_timeframe = getattr(mt5, _TIMEFRAME_MAP_NAMES[timeframe])
        rates = mt5.copy_rates_from_pos(symbol.name, mt5_timeframe, 0, count)
        if rates is None:
            raise MT5ConnectionError(f"copy_rates_from_pos failed: {mt5.last_error()}")
        candles = [
            Candle(
                timestamp=datetime.fromtimestamp(r["time"], tz=timezone.utc),
                open=float(r["open"]), high=float(r["high"]), low=float(r["low"]), close=float(r["close"]),
                volume=float(r["tick_volume"]), spread=float(r["spread"]) * symbol.pip_size,
            )
            for r in rates
        ]
        return CandleSeries(symbol=symbol, timeframe=timeframe, candles=candles)

    def get_ticks(self, symbol: Symbol, start: datetime, end: datetime) -> list[Tick]:
        mt5 = self._require_mt5()
        raw = mt5.copy_ticks_range(symbol.name, start, end, mt5.COPY_TICKS_ALL)
        if raw is None:
            raise MT5ConnectionError(f"copy_ticks_range failed: {mt5.last_error()}")
        return [
            Tick(timestamp=datetime.fromtimestamp(t["time"], tz=timezone.utc), bid=float(t["bid"]),
                 ask=float(t["ask"]), volume=float(t["volume"]))
            for t in raw
        ]

    def get_latest_tick(self, symbol: Symbol) -> Tick:
        mt5 = self._require_mt5()
        tick = mt5.symbol_info_tick(symbol.name)
        if tick is None:
            raise MT5ConnectionError(f"symbol_info_tick failed: {mt5.last_error()}")
        return Tick(timestamp=datetime.fromtimestamp(tick.time, tz=timezone.utc), bid=tick.bid, ask=tick.ask,
                    volume=float(tick.volume))

    def get_account_state(self) -> AccountState:
        """Not part of MarketDataProvider — only meaningful when MT5 is the
        active source. Reflects the real broker account; never used as the
        default capital basis for sizing (see core/risk/risk_manager.py)."""
        mt5 = self._require_mt5()
        info = mt5.account_info()
        if info is None:
            raise MT5ConnectionError(f"account_info failed: {mt5.last_error()}")
        return AccountState(balance=info.balance, equity=info.equity, margin=info.margin, currency=info.currency)

    def _require_mt5(self):
        if self._mt5 is None:
            raise MT5ConnectionError("call connect() before using this adapter")
        return self._mt5
