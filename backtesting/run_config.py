"""BacktestRunConfig — parameterizes one backtest run.

`strategy_set` is the single knob that lets the same engine test Classic,
SMC, ICT and every combination (Classic+SMC, Classic+ICT, SMC+ICT, ALL)
without any code change. `train_range`/`test_range` are present now (even
though v1 doesn't enforce their separation) so Out-of-Sample testing can be
added later without touching the engine.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.market_data.models import Timeframe
from core.signals.enums import StrategyCategory

STRATEGY_COMBINATIONS: dict[str, set[StrategyCategory] | None] = {
    "Classic": {StrategyCategory.CLASSIC},
    "SMC": {StrategyCategory.SMC},
    "ICT": {StrategyCategory.ICT},
    "Classic+SMC": {StrategyCategory.CLASSIC, StrategyCategory.SMC},
    "Classic+ICT": {StrategyCategory.CLASSIC, StrategyCategory.ICT},
    "SMC+ICT": {StrategyCategory.SMC, StrategyCategory.ICT},
    "All": None,  # None => no category filter, every enabled strategy runs
}


@dataclass(frozen=True)
class BacktestRunConfig:
    symbol_name: str
    entry_timeframe: Timeframe
    strategy_set: str  # a key from STRATEGY_COMBINATIONS
    start: datetime
    end: datetime
    train_range: tuple[datetime, datetime] | None = None
    test_range: tuple[datetime, datetime] | None = None

    @property
    def categories(self) -> set[StrategyCategory] | None:
        return STRATEGY_COMBINATIONS[self.strategy_set]
