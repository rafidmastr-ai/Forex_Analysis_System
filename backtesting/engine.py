"""BacktestEngine — walk-forward, Point-in-Time simulation.

For each closed entry-timeframe candle in the run window, the engine
builds an AnalysisContext whose data is sliced strictly at that candle's
close (never later), runs the Strategy Selection Engine against it, and —
if a setup was produced — simulates the outcome using only the candles
that follow (the one place "the future" is legitimately used: to score
what actually happened to a trade already opened, never to decide whether
to open it).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from backtesting.run_config import BacktestRunConfig
from core.context.analysis_context import AnalysisContext
from core.context.timeframe_selector import TimeframeSelector
from core.market_data.models import CandleSeries, Symbol
from core.market_data.provider_interface import MarketDataProvider
from core.selection.strategy_selection_engine import StrategySelectionEngine
from core.signals.enums import Direction, SetupStatus
from core.signals.selected_setup import SelectedSetup
from core.strategies.registry import StrategyRegistry


@dataclass
class TradeOutcome:
    setup: SelectedSetup
    opened_at: datetime
    hit: str  # "TP1" | "TP2" | "SL" | "NONE" (window ended before either was hit)


@dataclass
class BacktestReport:
    run_config: BacktestRunConfig
    outcomes: list[TradeOutcome] = field(default_factory=list)

    @property
    def total_setups(self) -> int:
        return len(self.outcomes)

    @property
    def win_rate_tp1(self) -> float:
        if not self.outcomes:
            return 0.0
        wins = sum(1 for o in self.outcomes if o.hit in ("TP1", "TP2"))
        return wins / len(self.outcomes)


class BacktestEngine:
    def __init__(
        self,
        provider: MarketDataProvider,
        registry: StrategyRegistry,
        selection_engine: StrategySelectionEngine,
        timeframes_config: dict | None = None,
    ):
        self._provider = provider
        self._registry = registry
        self._selection_engine = selection_engine
        # Falls back to the entry timeframe for all three roles only if no
        # config is supplied (keeps older call sites/tests working); real
        # runs should always pass config.timeframes so Higher/Middle are
        # genuinely different timeframes, not the entry series reused.
        self._timeframes_config = timeframes_config

    def run(self, config: BacktestRunConfig) -> BacktestReport:
        symbol: Symbol = self._provider.get_symbol_info(config.symbol_name)
        entry_series = self._provider.get_ohlcv(symbol, config.entry_timeframe, count=100000)

        if self._timeframes_config is not None:
            selector = TimeframeSelector(self._timeframes_config)
            resolved = selector.select()
            higher_series = self._provider.get_ohlcv(symbol, resolved.higher, count=100000)
            middle_series = self._provider.get_ohlcv(symbol, resolved.middle, count=100000)
        else:
            higher_series = self._provider.get_ohlcv(symbol, config.entry_timeframe, count=100000)
            middle_series = self._provider.get_ohlcv(symbol, config.entry_timeframe, count=100000)

        strategies = [s() for s in self._registry.enabled_by_category(config.categories)]
        report = BacktestReport(run_config=config)

        window = [c for c in entry_series.candles if config.start <= c.timestamp <= config.end]
        for candle in window:
            as_of = candle.timestamp
            context = AnalysisContext(
                symbol=symbol,
                current_bid=candle.close,
                current_ask=candle.close + (candle.spread or 0.0),
                session="unspecified",
                higher_timeframe=higher_series.sliced_as_of(as_of),
                middle_timeframe=middle_series.sliced_as_of(as_of),
                entry_timeframe=entry_series.sliced_as_of(as_of),
                as_of=as_of,
            )
            setup = self._selection_engine.run(strategies, context)
            if setup is None or setup.status != SetupStatus.SELECTED:
                continue

            future_candles = [c for c in entry_series.candles if c.timestamp > as_of]
            hit = self._simulate_outcome(setup, future_candles)
            report.outcomes.append(TradeOutcome(setup=setup, opened_at=as_of, hit=hit))

        return report

    @staticmethod
    def _simulate_outcome(setup: SelectedSetup, future_candles: list) -> str:
        for candle in future_candles:
            if setup.direction == Direction.BUY:
                if candle.low <= setup.stop_loss:
                    return "SL"
                if candle.high >= setup.take_profit_2:
                    return "TP2"
                if candle.high >= setup.take_profit_1:
                    return "TP1"
            else:
                if candle.high >= setup.stop_loss:
                    return "SL"
                if candle.low <= setup.take_profit_2:
                    return "TP2"
                if candle.low <= setup.take_profit_1:
                    return "TP1"
        return "NONE"
