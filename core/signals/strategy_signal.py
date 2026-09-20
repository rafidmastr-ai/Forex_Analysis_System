"""StrategySignal — the raw, unsized opinion of a single strategy.

A strategy only says "I see this setup here" — it never knows about lot
size or capital. Price levels (entry/invalidation/targets) come from the
strategy's own technical read of the market, not from Risk Management.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.signals.enums import Direction, StrategyCategory


@dataclass(frozen=True)
class PriceZone:
    low: float
    high: float

    @property
    def mid(self) -> float:
        return (self.low + self.high) / 2


@dataclass(frozen=True)
class StrategySignal:
    strategy_id: str
    category: StrategyCategory
    direction: Direction
    suggested_entry_zone: PriceZone
    suggested_stop_loss: float
    suggested_take_profit_1: float
    suggested_take_profit_2: float
    rationale: list[str]
    raw_score_components: dict[str, Any] = field(default_factory=dict)
    generated_at: datetime | None = None
