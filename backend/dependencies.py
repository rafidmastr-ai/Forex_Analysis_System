"""Dependency injection wiring.

This module is the ONLY place that decides which MarketDataProvider
implementation is actually active (mock / historical_file / mt5), based on
config.data_source.provider. Everything above this line — routers, the
Core Analysis Engine — depends only on the MarketDataProvider interface.
"""
from __future__ import annotations

from functools import lru_cache

import core.strategies.bootstrap  # noqa: F401 — registers Classic/SMC/ICT on import
from adapters.historical_file.file_adapter import HistoricalFileMarketDataProvider
from adapters.mock.mock_adapter import MockMarketDataProvider
from backend.config import Settings, get_settings
from core.confidence.confidence_engine import ConfidenceEngine
from core.market_data.models import Symbol
from core.market_data.provider_interface import MarketDataProvider
from core.market_data.validation import ValidatingMarketDataProvider
from core.risk.risk_manager import RiskManager
from core.selection.strategy_selection_engine import StrategySelectionEngine
from core.strategies.registry import StrategyRegistry
from core.strategies.registry import registry as _strategy_registry


def _symbols_from_config(settings: Settings) -> dict[str, Symbol]:
    return {
        entry["name"]: Symbol(
            name=entry["name"],
            pip_size=entry["pip_size"],
            digits=entry["digits"],
            contract_size=entry["contract_size"],
        )
        for entry in settings.symbols
    }


@lru_cache
def get_market_data_provider() -> MarketDataProvider:
    settings = get_settings()
    provider_name = settings.data_source_provider

    base: MarketDataProvider
    if provider_name == "mock":
        base = MockMarketDataProvider()
    elif provider_name == "historical_file":
        historical_dir = settings.data_source.get("historical_dir", "data/historical")
        base = HistoricalFileMarketDataProvider(data_dir=historical_dir, symbols=_symbols_from_config(settings))
    elif provider_name == "mt5":
        from adapters.mt5.mt5_data_adapter import MT5DataMarketDataProvider

        mt5_provider = MT5DataMarketDataProvider()
        mt5_provider.connect()
        base = mt5_provider
    else:
        raise ValueError(f"unknown data_source.provider: {provider_name}")

    max_spread = settings.data.get("max_spread", {})
    return ValidatingMarketDataProvider(base, max_spread_by_symbol=max_spread)


def get_strategy_registry() -> StrategyRegistry:
    return _strategy_registry


@lru_cache
def get_confidence_engine() -> ConfidenceEngine:
    settings = get_settings()
    return ConfidenceEngine(
        thresholds=settings.confidence["thresholds"],
        multi_strategy_agreement_bonus=settings.confidence["multi_strategy_agreement_bonus"],
    )


@lru_cache
def get_selection_engine() -> StrategySelectionEngine:
    settings = get_settings()
    return StrategySelectionEngine(
        confidence_engine=get_confidence_engine(),
        filters=[],
        min_risk_reward=settings.risk["min_risk_reward"],
    )


@lru_cache
def get_risk_manager() -> RiskManager:
    return RiskManager()


def get_settings_dep() -> Settings:
    return get_settings()
