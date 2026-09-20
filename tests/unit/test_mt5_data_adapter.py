"""Unit tests for MT5DataMarketDataProvider using a stub MetaTrader5 module.

We deliberately do NOT try to install MetaTrader5, Wine, or run a real MT5
terminal here — that is impossible in this Linux Cloud environment by
design (see docs/architecture.md). Instead we inject a fake module into
sys.modules that mimics the small slice of the real package's shape this
adapter relies on, so the conversion logic (MT5 raw data -> unified
Candle/Tick/Symbol/AccountState models) is verified without any real
broker connection. Real, live MT5 behavior can only be verified on the
Windows runtime (tests/mt5_integration/).
"""
from __future__ import annotations

import sys
import types
from datetime import datetime, timezone

import pytest

from adapters.mt5.mt5_data_adapter import MT5ConnectionError, MT5DataMarketDataProvider
from core.market_data.models import Timeframe


class _SymbolInfo:
    def __init__(self):
        self.point = 0.00001
        self.digits = 5
        self.trade_contract_size = 100000.0
        self.trade_tick_size = 0.00001
        self.trade_tick_value = 1.0
        self.volume_min = 0.01
        self.volume_max = 100.0
        self.volume_step = 0.01


class _Tick:
    def __init__(self, time_, bid, ask, volume):
        self.time, self.bid, self.ask, self.volume = time_, bid, ask, volume


class _AccountInfo:
    def __init__(self):
        self.balance = 10_000.0
        self.equity = 10_050.0
        self.margin = 200.0
        self.currency = "USD"


def _make_fake_mt5(*, login_succeeds: bool = True, initialize_succeeds: bool = True):
    fake = types.SimpleNamespace()
    fake.TIMEFRAME_M1 = 1
    fake.TIMEFRAME_M5 = 5
    fake.TIMEFRAME_M15 = 15
    fake.TIMEFRAME_M30 = 30
    fake.TIMEFRAME_H1 = 60
    fake.TIMEFRAME_H4 = 240
    fake.TIMEFRAME_D1 = 1440
    fake.COPY_TICKS_ALL = 0

    fake.initialize = lambda *a, **k: initialize_succeeds
    fake.login = lambda *a, **k: login_succeeds
    fake.last_error = lambda: (1, "stub error")
    fake.terminal_info = lambda: types.SimpleNamespace(connected=True)
    fake.symbol_info = lambda name: _SymbolInfo() if name == "EURUSD" else None
    fake.account_info = lambda: _AccountInfo()

    epoch = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp())
    fake.copy_rates_from_pos = lambda symbol, timeframe, start, count: [
        {"time": epoch + i * 60, "open": 1.10, "high": 1.101, "low": 1.099, "close": 1.1005,
         "tick_volume": 100, "spread": 2}
        for i in range(count)
    ]
    fake.copy_ticks_range = lambda symbol, start, end, flags: [
        {"time": epoch, "bid": 1.1000, "ask": 1.1001, "volume": 1},
        {"time": epoch + 1, "bid": 1.1001, "ask": 1.1002, "volume": 2},
    ]
    fake.symbol_info_tick = lambda name: _Tick(epoch, 1.1000, 1.1001, 5)
    return fake


@pytest.fixture
def mt5_env(monkeypatch):
    monkeypatch.setenv("MT5_LOGIN", "12345")
    monkeypatch.setenv("MT5_PASSWORD", "secret")
    monkeypatch.setenv("MT5_SERVER", "Broker-Demo")
    yield
    sys.modules.pop("MetaTrader5", None)


def test_connect_succeeds_with_valid_credentials(mt5_env):
    sys.modules["MetaTrader5"] = _make_fake_mt5()
    adapter = MT5DataMarketDataProvider()

    adapter.connect()

    assert adapter.is_connected() is True


def test_connect_fails_without_env_vars(monkeypatch):
    monkeypatch.delenv("MT5_LOGIN", raising=False)
    monkeypatch.delenv("MT5_PASSWORD", raising=False)
    monkeypatch.delenv("MT5_SERVER", raising=False)
    sys.modules["MetaTrader5"] = _make_fake_mt5()
    adapter = MT5DataMarketDataProvider()

    with pytest.raises(MT5ConnectionError):
        adapter.connect()
    sys.modules.pop("MetaTrader5", None)


def test_connect_fails_when_login_rejected(mt5_env):
    sys.modules["MetaTrader5"] = _make_fake_mt5(login_succeeds=False)
    adapter = MT5DataMarketDataProvider()

    with pytest.raises(MT5ConnectionError):
        adapter.connect()


def test_get_symbol_info_maps_full_broker_spec(mt5_env):
    sys.modules["MetaTrader5"] = _make_fake_mt5()
    adapter = MT5DataMarketDataProvider()
    adapter.connect()

    symbol = adapter.get_symbol_info("EURUSD")

    assert symbol.name == "EURUSD"
    assert symbol.tick_size == 0.00001
    assert symbol.tick_value == 1.0
    assert symbol.volume_min == 0.01
    assert symbol.volume_max == 100.0
    assert symbol.volume_step == 0.01
    assert symbol.point == 0.00001


def test_get_symbol_info_unknown_symbol_raises(mt5_env):
    sys.modules["MetaTrader5"] = _make_fake_mt5()
    adapter = MT5DataMarketDataProvider()
    adapter.connect()

    with pytest.raises(ValueError):
        adapter.get_symbol_info("UNKNOWN")


def test_get_ohlcv_converts_rates_to_candles(mt5_env):
    sys.modules["MetaTrader5"] = _make_fake_mt5()
    adapter = MT5DataMarketDataProvider()
    adapter.connect()
    symbol = adapter.get_symbol_info("EURUSD")

    series = adapter.get_ohlcv(symbol, Timeframe.M15, count=10)

    assert len(series) == 10
    assert series.candles[0].timestamp.tzinfo is not None
    assert series.candles[0].close == 1.1005


def test_get_ticks_converts_raw_ticks(mt5_env):
    sys.modules["MetaTrader5"] = _make_fake_mt5()
    adapter = MT5DataMarketDataProvider()
    adapter.connect()
    symbol = adapter.get_symbol_info("EURUSD")

    ticks = adapter.get_ticks(symbol, datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 2, tzinfo=timezone.utc))

    assert len(ticks) == 2
    assert ticks[0].bid == 1.1000 and ticks[0].ask == 1.1001


def test_get_latest_tick_converts_single_tick(mt5_env):
    sys.modules["MetaTrader5"] = _make_fake_mt5()
    adapter = MT5DataMarketDataProvider()
    adapter.connect()
    symbol = adapter.get_symbol_info("EURUSD")

    tick = adapter.get_latest_tick(symbol)

    assert tick.bid == 1.1000
    assert tick.ask == 1.1001


def test_get_account_state_maps_balance_fields(mt5_env):
    sys.modules["MetaTrader5"] = _make_fake_mt5()
    adapter = MT5DataMarketDataProvider()
    adapter.connect()

    account = adapter.get_account_state()

    assert account.balance == 10_000.0
    assert account.equity == 10_050.0
    assert account.currency == "USD"


def test_using_adapter_before_connect_raises():
    adapter = MT5DataMarketDataProvider()
    with pytest.raises(MT5ConnectionError):
        adapter.get_symbol_info("EURUSD")


def test_connect_without_package_installed_raises_clear_error(monkeypatch):
    # Simulate the real Linux Cloud situation: no MetaTrader5 package at all.
    monkeypatch.setenv("MT5_LOGIN", "1")
    monkeypatch.setenv("MT5_PASSWORD", "x")
    monkeypatch.setenv("MT5_SERVER", "s")
    sys.modules.pop("MetaTrader5", None)
    monkeypatch.setitem(sys.modules, "MetaTrader5", None)  # forces ImportError on `import MetaTrader5`

    adapter = MT5DataMarketDataProvider()
    with pytest.raises(MT5ConnectionError):
        adapter.connect()
