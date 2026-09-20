"""BaseAlgorithm — low-level analytical building blocks used by strategies.

An algorithm computes one well-defined piece of market structure (trend
direction, an order block, a liquidity sweep, an indicator value...). It
never knows about risk, capital, or trading — only about price data.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from core.context.analysis_context import AnalysisContext


@dataclass
class AlgorithmResult:
    name: str
    values: dict[str, Any] = field(default_factory=dict)


class BaseAlgorithm(ABC):
    name: str

    # Declarative parameter schema, so a future optimizer can search this
    # space without touching the algorithm's code (see architecture note on
    # Parameter Optimization).
    parameters: dict[str, Any] = {}

    @abstractmethod
    def compute(self, context: AnalysisContext) -> AlgorithmResult:
        ...
