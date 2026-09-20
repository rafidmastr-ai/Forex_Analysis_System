"""Runs all seven strategy-set combinations for the same symbol/window and
returns their reports side by side, so results are directly comparable.
"""
from __future__ import annotations

from datetime import datetime

from backtesting.engine import BacktestEngine, BacktestReport
from backtesting.run_config import STRATEGY_COMBINATIONS, BacktestRunConfig
from core.market_data.models import Timeframe


def run_all_combinations(
    engine: BacktestEngine, symbol_name: str, entry_timeframe: Timeframe, start: datetime, end: datetime
) -> dict[str, BacktestReport]:
    reports: dict[str, BacktestReport] = {}
    for combo_name in STRATEGY_COMBINATIONS:
        config = BacktestRunConfig(
            symbol_name=symbol_name, entry_timeframe=entry_timeframe, strategy_set=combo_name, start=start, end=end
        )
        reports[combo_name] = engine.run(config)
    return reports
