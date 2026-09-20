"""BaseFilter — post-processes a raw StrategySignal before it reaches the
Confidence Engine. A filter can reject a signal outright or adjust its
confidence contribution; it never invents price levels.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from core.context.analysis_context import AnalysisContext


@dataclass
class FilterResult:
    passed: bool
    reason: str
    confidence_adjustment: int = 0  # added to/subtracted from the raw confidence score


class BaseFilter(ABC):
    name: str

    @abstractmethod
    def apply(self, signal: "StrategySignal", context: AnalysisContext) -> FilterResult:  # noqa: F821
        ...
