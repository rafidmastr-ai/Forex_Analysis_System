"""StrategyRegistry — central catalogue of available strategies.

Strategies register themselves via the @register_strategy decorator so the
Strategy Selection Engine and the Backend API can discover what's available
without a hand-maintained import list.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.signals.enums import StrategyCategory
from core.strategies.base import BaseStrategy


@dataclass
class StrategyMetadata:
    strategy_id: str
    category: StrategyCategory
    enabled: bool = True


class StrategyRegistry:
    def __init__(self) -> None:
        self._strategies: dict[str, type[BaseStrategy]] = {}
        self._metadata: dict[str, StrategyMetadata] = {}

    def register(self, strategy_cls: type[BaseStrategy], enabled: bool = True) -> type[BaseStrategy]:
        strategy_id = strategy_cls.strategy_id
        self._strategies[strategy_id] = strategy_cls
        self._metadata[strategy_id] = StrategyMetadata(
            strategy_id=strategy_id, category=strategy_cls.category, enabled=enabled
        )
        return strategy_cls

    def get(self, strategy_id: str) -> type[BaseStrategy]:
        return self._strategies[strategy_id]

    def all(self) -> list[StrategyMetadata]:
        return list(self._metadata.values())

    def enabled_by_category(self, categories: set[StrategyCategory] | None = None) -> list[type[BaseStrategy]]:
        result = []
        for strategy_id, meta in self._metadata.items():
            if not meta.enabled:
                continue
            if categories is not None and meta.category not in categories:
                continue
            result.append(self._strategies[strategy_id])
        return result

    def set_enabled(self, strategy_id: str, enabled: bool) -> None:
        self._metadata[strategy_id].enabled = enabled


registry = StrategyRegistry()


def register_strategy(cls: type[BaseStrategy]) -> type[BaseStrategy]:
    return registry.register(cls)
