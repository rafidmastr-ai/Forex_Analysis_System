"""Wires a single strategy instance (with specific weights/disabled
components) into a real BacktestEngine run — the "evaluate" function the
weight search, ablation, robustness and combination testing all call.
"""
from __future__ import annotations

from datetime import datetime
from typing import cast

from backtesting.engine import BacktestEngine, BacktestReport
from backtesting.run_config import BacktestRunConfig
from core.market_data.models import Timeframe
from core.market_data.provider_interface import MarketDataProvider
from core.selection.strategy_selection_engine import StrategySelectionEngine
from core.strategies.base import BaseStrategy
from core.strategies.registry import StrategyRegistry
from optimization.objective import PerformanceMetrics, compute_metrics


class FixedStrategyRegistry(StrategyRegistry):
    """Serves one or more already-constructed strategy instances regardless
    of `categories` — used to run a specific weight/ablation configuration
    that the normal @register_strategy class-level registry has no way to
    express (it only knows about default-constructed strategies)."""

    def __init__(self, strategies: list[BaseStrategy]):
        super().__init__()
        self._fixed_strategies = strategies

    def enabled_by_category(self, categories=None):
        # Each element is a zero-arg factory returning the fixed instance —
        # what BacktestEngine actually calls (`s()`) — not a class, so this
        # is cast rather than literally typed as `type[BaseStrategy]`.
        return cast("list[type[BaseStrategy]]", [(lambda inst=s: inst) for s in self._fixed_strategies])


def run_backtest(
    strategies: list[BaseStrategy],
    provider: MarketDataProvider,
    selection_engine: StrategySelectionEngine,
    symbol_name: str,
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
    timeframes_config: dict,
    lookback_bars: dict,
    min_confidence: int | None,
) -> BacktestReport:
    registry = FixedStrategyRegistry(strategies)
    engine = BacktestEngine(
        provider=provider, registry=registry, selection_engine=selection_engine,
        timeframes_config=timeframes_config, lookback_bars=lookback_bars, min_confidence=min_confidence,
    )
    # strategy_set is irrelevant here (FixedStrategyRegistry ignores category
    # filtering) but BacktestRunConfig requires a valid key; "All" reads
    # correctly in any log/report referencing this config.
    config = BacktestRunConfig(symbol_name=symbol_name, entry_timeframe=timeframe, strategy_set="All", start=start, end=end)
    return engine.run(config)


def evaluate_metrics(
    strategies: list[BaseStrategy],
    provider: MarketDataProvider,
    selection_engine: StrategySelectionEngine,
    symbol_name: str,
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
    timeframes_config: dict,
    lookback_bars: dict,
    min_confidence: int | None,
) -> PerformanceMetrics:
    report = run_backtest(strategies, provider, selection_engine, symbol_name, timeframe, start, end,
                           timeframes_config, lookback_bars, min_confidence)
    return compute_metrics(report.outcomes)
