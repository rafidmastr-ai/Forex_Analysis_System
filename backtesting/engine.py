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
from datetime import datetime, timedelta

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
    r_multiple: float  # realized R: risk_reward_tp1/tp2 on a win, -1.0 on SL, 0.0 on NONE (excluded from R stats)
    closed_at: datetime | None = None  # timestamp of the candle that resolved the trade; None for "NONE" (still open) — purely descriptive (duration reporting), never read by any decision logic


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

    @property
    def resolved_outcomes(self) -> list[TradeOutcome]:
        """Outcomes that actually resolved (hit TP1/TP2/SL) before the run
        window ended — "NONE" trades are still open and excluded from any
        R-based statistic, not treated as a loss or a scratch."""
        return [o for o in self.outcomes if o.hit != "NONE"]


class BacktestEngine:
    def __init__(
        self,
        provider: MarketDataProvider,
        registry: StrategyRegistry,
        selection_engine: StrategySelectionEngine,
        timeframes_config: dict | None = None,
        lookback_bars: dict | None = None,
        min_confidence: int | None = None,
    ):
        self._provider = provider
        self._registry = registry
        self._selection_engine = selection_engine
        # A confidence floor for actually TAKING a setup in this run — None
        # (the default, and the only mode used outside optimization/) means
        # every setup that clears the min-R:R floor is traded, matching
        # production /analyze (confidence is informational there, it never
        # gates the trade). The optimization framework sets this so that
        # different component weights can actually change which trades are
        # taken, not just relabel the same fixed trade set — otherwise
        # weight optimization would have no way to affect performance at all.
        self._min_confidence = min_confidence
        # Falls back to the entry timeframe for all three roles only if no
        # config is supplied (keeps older call sites/tests working); real
        # runs should always pass config.timeframes so Higher/Middle are
        # genuinely different timeframes, not the entry series reused.
        self._timeframes_config = timeframes_config
        # Mirrors config.data.lookback_bars, the same bound the live
        # /analyze flow fetches (backend/routers/signals.py). Without this,
        # each simulated bar would hand strategies the ENTIRE history seen
        # so far instead of the bounded recent window they'd actually get
        # live — both a correctness mismatch with production behavior and,
        # since several algorithms rescan the full visible window every
        # step, an unbounded-growth cost that makes a real multi-year
        # backtest impractically slow. `None` keeps the old unbounded
        # behavior for callers/tests that don't pass it.
        self._lookback_bars = lookback_bars

    def run(self, config: BacktestRunConfig) -> BacktestReport:
        symbol: Symbol = self._provider.get_symbol_info(config.symbol_name)
        entry_series = self._provider.get_ohlcv(symbol, config.entry_timeframe, count=100000)

        if self._timeframes_config is not None:
            selector = TimeframeSelector(self._timeframes_config)
            entry_mapping = self._timeframes_config.get("entry_mapping")
            if entry_mapping is not None and config.entry_timeframe.value in entry_mapping:
                # Entry-timeframe-aware resolution (see TimeframeSelector.resolve_for_entry):
                # required once the backtest tests entry timeframes other than the single
                # one production ever requests -- the old static default_mapping (always
                # Higher=H4/Middle=H1 regardless of entry) silently produced a Higher/Middle
                # series at or below the entry timeframe's own resolution for some entries.
                resolved = selector.resolve_for_entry(config.entry_timeframe)
            else:
                # Backward-compatible fallback for any caller/config that doesn't supply
                # entry_mapping (e.g. live /analyze's own call site, which never goes
                # through BacktestEngine at all, and older tests/configs here).
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
            # `as_of` is this candle's OPEN timestamp (see Candle.timestamp's own
            # contract) -- current_bid/ask below deliberately use its CLOSE price
            # (candle.close), i.e. the decision is genuinely being made at the
            # instant this candle closes. CandleSeries.sliced_as_of() gates each
            # series on ITS OWN candles' close time, so the true "closed as of"
            # instant to slice against is this entry candle's own close, not its
            # open -- passing the open through unchanged would (for any series in
            # a DIFFERENT, coarser timeframe than the entry one) let a still-
            # forming Higher/Middle candle leak its not-yet-known high/low/close
            # into the context. `as_of` itself is untouched for everything else
            # below (opened_at, future_candles, AnalysisContext.as_of, kill
            # zones/session gating) -- only the three sliced_as_of() calls need
            # the true close instant.
            entry_closed_at = as_of + timedelta(minutes=config.entry_timeframe.minutes)
            context = AnalysisContext(
                symbol=symbol,
                current_bid=candle.close,
                current_ask=candle.close + (candle.spread or 0.0),
                session="unspecified",
                higher_timeframe=self._bounded(higher_series.sliced_as_of(entry_closed_at), "higher"),
                middle_timeframe=self._bounded(middle_series.sliced_as_of(entry_closed_at), "middle"),
                entry_timeframe=self._bounded(entry_series.sliced_as_of(entry_closed_at), "entry"),
                as_of=as_of,
            )
            setup = self._selection_engine.run(strategies, context)
            if setup is None or setup.status != SetupStatus.SELECTED:
                continue
            if self._min_confidence is not None and setup.confidence_score < self._min_confidence:
                continue

            future_candles = [c for c in entry_series.candles if c.timestamp > as_of]
            hit, r_multiple, closed_at = self._simulate_outcome(setup, future_candles)
            report.outcomes.append(TradeOutcome(setup=setup, opened_at=as_of, hit=hit, r_multiple=r_multiple, closed_at=closed_at))

        return report

    def _bounded(self, series: CandleSeries, role: str) -> CandleSeries:
        if self._lookback_bars is None:
            return series
        max_bars = self._lookback_bars[role]
        if len(series.candles) <= max_bars:
            return series
        return CandleSeries(symbol=series.symbol, timeframe=series.timeframe, candles=series.candles[-max_bars:])

    @staticmethod
    def _simulate_outcome(setup: SelectedSetup, future_candles: list) -> tuple[str, float, datetime | None]:
        for candle in future_candles:
            if setup.direction == Direction.BUY:
                if candle.low <= setup.stop_loss:
                    return "SL", -1.0, candle.timestamp
                if candle.high >= setup.take_profit_2:
                    return "TP2", setup.risk_reward_tp2, candle.timestamp
                if candle.high >= setup.take_profit_1:
                    return "TP1", setup.risk_reward_tp1, candle.timestamp
            else:
                if candle.high >= setup.stop_loss:
                    return "SL", -1.0, candle.timestamp
                if candle.low <= setup.take_profit_2:
                    return "TP2", setup.risk_reward_tp2, candle.timestamp
                if candle.low <= setup.take_profit_1:
                    return "TP1", setup.risk_reward_tp1, candle.timestamp
        return "NONE", 0.0, None
