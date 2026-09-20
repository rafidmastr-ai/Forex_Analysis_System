"""End-to-end tests through the real /analyze HTTP endpoint: real
AnalysisContext assembly, real ConfidenceEngine, real StrategySelectionEngine
(with the actual config.risk.min_risk_reward = 1.5 floor), real RiskManager
— only the market-data provider and the strategy registry are swapped for
controllable fakes, via FastAPI dependency overrides. This is the layer
above tests/unit/: it proves the pieces work TOGETHER through the API
exactly as a client would call it, not just in isolation.

The selection engine's FILTERS specifically are also overridden to empty
(same confidence engine and min_risk_reward floor as production) for every
test in this file except the one dedicated to it
(test_volatility_filter_rejects_signal_through_the_real_endpoint): once
VolatilityRegimeFilter was wired into production (Task 45, see
backend/dependencies.py), MockMarketDataProvider's seeded random-walk data
happened to classify as "high" volatility regime at these tests' fixed
evaluation instant, silently swallowing every fixture signal these tests
exist to check RR-math/confidence-aggregation/freshness-field behavior
with — none of which is what they're testing, so isolating the filter
here is the same reasoning as isolating the provider/registry, not a way
to dodge the new behavior (which gets its own real, unoverridden test).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from adapters.mock.mock_adapter import MockMarketDataProvider
from backend.dependencies import (
    get_confidence_engine,
    get_market_data_provider,
    get_selection_engine,
    get_settings_dep,
    get_strategy_registry,
)
from backend.main import app
from core.market_data.models import Candle, CandleSeries, Symbol, Tick
from core.market_data.provider_interface import MarketDataProvider
from core.market_data.validation import ValidatingMarketDataProvider
from core.selection.strategy_selection_engine import StrategySelectionEngine
from core.signals.enums import Direction, StrategyCategory
from core.signals.strategy_signal import PriceZone, StrategySignal
from core.strategies.base import BaseStrategy
from core.strategies.registry import StrategyRegistry

client = TestClient(app)


class _FixedRegistry(StrategyRegistry):
    """Serves a fixed, caller-supplied list of already-constructed strategy
    instances instead of discovering them via @register_strategy."""

    def __init__(self, strategies: list[BaseStrategy]):
        super().__init__()
        self._fixed = strategies

    def enabled_by_category(self, categories=None):
        return [(lambda inst=s: inst) for s in self._fixed]


def _fixed_strategy(strategy_id, category, direction, entry, sl, tp1, tp2, base_confidence=70, extra=None):
    class _Fixed(BaseStrategy):
        def analyze(self, context):
            return StrategySignal(
                strategy_id=strategy_id, category=category, direction=direction,
                suggested_entry_zone=PriceZone(entry, entry), suggested_stop_loss=sl,
                suggested_take_profit_1=tp1, suggested_take_profit_2=tp2,
                rationale=[f"{strategy_id} fixture rationale"],
                raw_score_components={"base_confidence": base_confidence, **(extra or {})},
                generated_at=datetime.now(timezone.utc),
            )

    _Fixed.strategy_id = strategy_id
    _Fixed.category = category
    return _Fixed()


def _no_signal_strategy(strategy_id="no_signal", category=StrategyCategory.CLASSIC):
    class _NoSignal(BaseStrategy):
        def analyze(self, context):
            return None

    _NoSignal.strategy_id = strategy_id
    _NoSignal.category = category
    return _NoSignal()


class _BadDataProvider(MarketDataProvider):
    """Always returns a single candle with high < low — triggers the Data
    Validation Layer's critical failure path through the real endpoint."""

    def is_connected(self):
        return True

    def get_symbol_info(self, symbol_name):
        return Symbol(name=symbol_name, pip_size=0.0001, digits=5, contract_size=100000)

    def get_ohlcv(self, symbol, timeframe, count):
        bad = Candle(timestamp=datetime.now(timezone.utc), open=1.10, high=1.09, low=1.11, close=1.10, volume=100)
        return CandleSeries(symbol=symbol, timeframe=timeframe, candles=[bad])

    def get_ticks(self, symbol, start, end):
        return []

    def get_latest_tick(self, symbol):
        return Tick(timestamp=datetime.now(timezone.utc), bid=1.10, ask=1.1001)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _override_provider(base_provider):
    app.dependency_overrides[get_market_data_provider] = lambda: ValidatingMarketDataProvider(base_provider)


def _override_registry(strategies):
    app.dependency_overrides[get_strategy_registry] = lambda: _FixedRegistry(strategies)
    # Real confidence engine and min_risk_reward floor, filters emptied — see the module
    # docstring for why (isolating the volatility filter from unrelated mock-data fixtures).
    app.dependency_overrides[get_selection_engine] = lambda: StrategySelectionEngine(
        confidence_engine=get_confidence_engine(), filters=[], min_risk_reward=get_settings_dep().risk["min_risk_reward"],
    )


def _default_payload(**overrides):
    payload = {"symbol": "EURUSD", "risk_percent": 1.0, "lot_mode": "AUTO"}
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# BUY / SELL / NO TRADE
# ---------------------------------------------------------------------------

def test_end_to_end_buy_signal_with_capital():
    _override_provider(MockMarketDataProvider())
    _override_registry([_fixed_strategy("classic_x", StrategyCategory.CLASSIC, Direction.BUY,
                                         entry=1.1000, sl=1.0950, tp1=1.1075, tp2=1.1150)])

    resp = client.post("/analyze", json=_default_payload(capital=10000))

    assert resp.status_code == 200
    body = resp.json()
    assert body["direction"] == "BUY"
    assert body["status"] == "ACTIVE"
    assert body["entry"] == pytest.approx(1.1000)
    assert body["financial_disclaimer"] is None
    assert body["lot_size"] is not None
    assert body["risk_amount"] == pytest.approx(100.0)  # 1% of 10,000


def test_end_to_end_sell_signal():
    _override_provider(MockMarketDataProvider())
    _override_registry([_fixed_strategy("ict_x", StrategyCategory.ICT, Direction.SELL,
                                         entry=1.1000, sl=1.1050, tp1=1.0925, tp2=1.0850)])

    resp = client.post("/analyze", json=_default_payload(capital=5000))

    assert resp.status_code == 200
    body = resp.json()
    assert body["direction"] == "SELL"
    assert body["take_profit_1"] < body["entry"] < body["stop_loss"]


def test_end_to_end_no_trade_returns_no_setup_found_without_fake_levels():
    _override_provider(MockMarketDataProvider())
    _override_registry([_no_signal_strategy()])

    resp = client.post("/analyze", json=_default_payload())

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "NO_SETUP_FOUND"
    assert "entry" not in body
    assert "take_profit_1" not in body


# ---------------------------------------------------------------------------
# Dynamic R:R boundary: < 1.5, == 1.5, > 1.5 (config min_risk_reward = 1.5)
# ---------------------------------------------------------------------------

def test_rr_below_minimum_is_rejected():
    _override_provider(MockMarketDataProvider())
    # risk = 0.0050, reward to TP1 = 0.0060 -> RR = 1.2, below the 1.5 floor.
    _override_registry([_fixed_strategy("classic_x", StrategyCategory.CLASSIC, Direction.BUY,
                                         entry=1.1000, sl=1.0950, tp1=1.1060, tp2=1.1100)])

    resp = client.post("/analyze", json=_default_payload())

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "REJECTED_MIN_RISK_REWARD"
    assert body["min_risk_reward"] == 1.5


def test_rr_exactly_at_minimum_is_accepted():
    _override_provider(MockMarketDataProvider())
    # risk = 0.0050, reward to TP1 = 0.0075 -> RR = 1.5 exactly.
    _override_registry([_fixed_strategy("classic_x", StrategyCategory.CLASSIC, Direction.BUY,
                                         entry=1.1000, sl=1.0950, tp1=1.1075, tp2=1.1150)])

    resp = client.post("/analyze", json=_default_payload())

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ACTIVE"
    assert body["risk_reward_tp1"] == pytest.approx(1.5, abs=0.01)


def test_rr_above_minimum_is_accepted_and_not_forced_to_a_fixed_ratio():
    _override_provider(MockMarketDataProvider())
    # RR = 3.0 — proves the system doesn't clamp/round to a canonical ratio like 1:2.
    _override_registry([_fixed_strategy("classic_x", StrategyCategory.CLASSIC, Direction.BUY,
                                         entry=1.1000, sl=1.0950, tp1=1.1150, tp2=1.1300)])

    resp = client.post("/analyze", json=_default_payload())

    body = resp.json()
    assert body["status"] == "ACTIVE"
    assert body["risk_reward_tp1"] == pytest.approx(3.0, abs=0.01)


# ---------------------------------------------------------------------------
# Manual vs Auto lot, capital optional
# ---------------------------------------------------------------------------

def test_manual_lot_without_capital_still_computes_money_but_not_risk_percent():
    _override_provider(MockMarketDataProvider())
    _override_registry([_fixed_strategy("classic_x", StrategyCategory.CLASSIC, Direction.BUY,
                                         entry=1.1000, sl=1.0950, tp1=1.1075, tp2=1.1150)])

    resp = client.post("/analyze", json=_default_payload(lot_mode="MANUAL", lot_size=0.1))

    body = resp.json()
    assert body["lot_size"] == 0.1
    assert body["lot_source"] == "MANUAL"
    assert body["expected_profit_tp1"] is not None
    assert body["financial_disclaimer"] is not None  # can't compute risk % of capital


def test_auto_lot_without_capital_returns_technical_fields_but_no_money():
    _override_provider(MockMarketDataProvider())
    _override_registry([_fixed_strategy("classic_x", StrategyCategory.CLASSIC, Direction.BUY,
                                         entry=1.1000, sl=1.0950, tp1=1.1075, tp2=1.1150)])

    resp = client.post("/analyze", json=_default_payload())  # AUTO, no capital

    body = resp.json()
    assert body["status"] == "ACTIVE"
    assert body["entry"] == pytest.approx(1.1000)
    assert body["direction"] == "BUY"
    assert body["lot_size"] is None
    assert body["risk_amount"] is None
    assert body["expected_profit_tp1"] is None
    assert body["expected_profit_tp2"] is None
    assert body["expected_loss"] is None
    assert body["financial_disclaimer"] is not None


def test_manual_lot_missing_size_returns_422():
    _override_provider(MockMarketDataProvider())
    _override_registry([_no_signal_strategy()])

    resp = client.post("/analyze", json=_default_payload(lot_mode="MANUAL"))

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Agreeing / conflicting strategies
# ---------------------------------------------------------------------------

def test_agreeing_strategies_boost_confidence_end_to_end():
    _override_provider(MockMarketDataProvider())
    _override_registry([
        _fixed_strategy("classic_x", StrategyCategory.CLASSIC, Direction.BUY, 1.1000, 1.0950, 1.1075, 1.1150, base_confidence=60),
        _fixed_strategy("smc_x", StrategyCategory.SMC, Direction.BUY, 1.1000, 1.0950, 1.1075, 1.1150, base_confidence=60),
    ])

    resp = client.post("/analyze", json=_default_payload())

    body = resp.json()
    assert body["selected_strategy"] == "Combination"
    assert "SMC" in body["agreeing_strategies"]
    assert body["confidence_score"] > 60  # agreement bonus applied


def test_conflicting_strategies_are_reported_and_higher_confidence_wins():
    _override_provider(MockMarketDataProvider())
    _override_registry([
        _fixed_strategy("classic_x", StrategyCategory.CLASSIC, Direction.BUY, 1.1000, 1.0950, 1.1075, 1.1150, base_confidence=85),
        _fixed_strategy("ict_x", StrategyCategory.ICT, Direction.SELL, 1.1000, 1.1050, 1.0925, 1.0850, base_confidence=40),
    ])

    resp = client.post("/analyze", json=_default_payload())

    body = resp.json()
    assert body["direction"] == "BUY"
    assert "ICT" in body["conflicting_strategies"]


# ---------------------------------------------------------------------------
# Invalid / missing data, spread & timestamp issues surface through the API
# ---------------------------------------------------------------------------

def test_invalid_ohlc_data_surfaces_as_502_through_the_endpoint():
    _override_provider(_BadDataProvider())
    _override_registry([_no_signal_strategy()])

    resp = client.post("/analyze", json=_default_payload())

    assert resp.status_code == 502
    assert "validation" in resp.json()["detail"].lower()


def test_unknown_symbol_returns_404():
    _override_provider(MockMarketDataProvider())
    _override_registry([_no_signal_strategy()])

    resp = client.post("/analyze", json=_default_payload(symbol="NOT_A_SYMBOL"))

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Analysis freshness / validity window
# ---------------------------------------------------------------------------

def test_fresh_analysis_is_active_and_has_a_future_valid_until():
    _override_provider(MockMarketDataProvider())
    _override_registry([_fixed_strategy("classic_x", StrategyCategory.CLASSIC, Direction.BUY,
                                         1.1000, 1.0950, 1.1075, 1.1150)])

    resp = client.post("/analyze", json=_default_payload())

    body = resp.json()
    created_at = datetime.fromisoformat(body["created_at"])
    valid_until = datetime.fromisoformat(body["valid_until"])
    assert body["status"] == "ACTIVE"
    assert valid_until > created_at
    assert body["analysis_timestamp"] == body["created_at"]
    assert isinstance(body["current_bid"], float)
    assert isinstance(body["current_ask"], float)
    assert body["spread"] == pytest.approx(body["current_ask"] - body["current_bid"], abs=1e-9)


# ---------------------------------------------------------------------------
# VolatilityRegimeFilter really is wired into the production selection engine
# ---------------------------------------------------------------------------

class _HighVolatilityProvider(MarketDataProvider):
    """40 tiny-range candles (ATR seed period) followed by 20 candles with
    linearly growing range -- the tail ATR value ends up ranked highest in
    its own trailing window, so core.algorithms.volatility.classify_volatility
    reads "high" at the final candle. Verified directly against
    classify_volatility before being used here."""

    def is_connected(self):
        return True

    def get_symbol_info(self, symbol_name):
        return Symbol(name=symbol_name, pip_size=0.0001, digits=5, contract_size=100000)

    def get_ohlcv(self, symbol, timeframe, count):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        candles = [
            Candle(timestamp=base + timedelta(minutes=i), open=1.1000, high=1.1001, low=1.0999, close=1.1000, volume=100)
            for i in range(40)
        ]
        for i in range(20):
            r = 0.0005 + i * 0.0005
            candles.append(Candle(timestamp=base + timedelta(minutes=40 + i), open=1.1000, high=1.1000 + r,
                                   low=1.1000 - r, close=1.1000, volume=100))
        return CandleSeries(symbol=symbol, timeframe=timeframe, candles=candles)

    def get_ticks(self, symbol, start, end):
        return []

    def get_latest_tick(self, symbol):
        return Tick(timestamp=datetime.now(timezone.utc), bid=1.1000, ask=1.1001)


def test_volatility_filter_rejects_signal_through_the_real_endpoint():
    """Unlike every other test in this file, the selection engine is NOT
    overridden here -- this is the one test that exercises the real
    production get_selection_engine() (Task 45: VolatilityRegimeFilter
    wired into backend/dependencies.py) end-to-end through the actual
    /analyze endpoint."""
    app.dependency_overrides[get_market_data_provider] = lambda: ValidatingMarketDataProvider(_HighVolatilityProvider())
    app.dependency_overrides[get_strategy_registry] = lambda: _FixedRegistry(
        [_fixed_strategy("classic_x", StrategyCategory.CLASSIC, Direction.BUY, 1.1000, 1.0950, 1.1075, 1.1150)]
    )

    resp = client.post("/analyze", json=_default_payload())

    assert resp.status_code == 200
    assert resp.json()["status"] == "NO_SETUP_FOUND"
