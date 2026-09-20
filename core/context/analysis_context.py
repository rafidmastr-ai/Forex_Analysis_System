"""AnalysisContext — the single object every strategy/algorithm/filter reads.

Built once per analysis run by the Strategy Selection Engine (via the
internal timeframe selector), never assembled ad hoc downstream. Every
timeframe field here is an internal system decision — no user input ever
sets higher_timeframe/middle_timeframe/entry_timeframe.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.market_data.models import CandleSeries, Symbol


@dataclass(frozen=True)
class AnalysisContext:
    symbol: Symbol
    current_bid: float
    current_ask: float
    session: str  # matches a key under config.session.definitions
    higher_timeframe: CandleSeries
    middle_timeframe: CandleSeries
    entry_timeframe: CandleSeries
    as_of: datetime  # UTC instant this context is valid for — drives Point-in-Time behavior

    @property
    def current_price(self) -> float:
        return (self.current_bid + self.current_ask) / 2

    @property
    def spread(self) -> float:
        return self.current_ask - self.current_bid

    @property
    def market_data(self) -> CandleSeries:
        """Primary reference series for generic use — the entry timeframe."""
        return self.entry_timeframe
