"""Data Validation Layer.

Wraps any MarketDataProvider and enforces data quality before Core ever
sees a candle or tick. Implemented as a decorator so it is transparent to
callers and to every adapter (Mock, Historical File, MT5).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from core.market_data.models import Candle, CandleSeries, Symbol, Tick, Timeframe
from core.market_data.provider_interface import MarketDataProvider


class DataQualityError(Exception):
    """Raised when incoming market data fails a critical validation check."""


@dataclass
class ValidationReport:
    issues: list[str] = field(default_factory=list)
    gaps: list[tuple[datetime, datetime]] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not self.issues and not self.gaps

    def add(self, issue: str) -> None:
        self.issues.append(issue)


class ValidatingMarketDataProvider(MarketDataProvider):
    def __init__(self, wrapped: MarketDataProvider, max_spread_by_symbol: dict[str, float] | None = None):
        self._wrapped = wrapped
        self._max_spread_by_symbol = max_spread_by_symbol or {}
        self.last_report: ValidationReport | None = None

    def is_connected(self) -> bool:
        return self._wrapped.is_connected()

    def get_account_state(self):
        """Passthrough for adapters that expose it (currently MT5 only).
        Not part of the MarketDataProvider contract itself."""
        getter = getattr(self._wrapped, "get_account_state", None)
        if getter is None:
            raise AttributeError("the active data source does not expose account state")
        return getter()

    def get_symbol_info(self, symbol_name: str) -> Symbol:
        return self._wrapped.get_symbol_info(symbol_name)

    def get_ohlcv(self, symbol: Symbol, timeframe: Timeframe, count: int) -> CandleSeries:
        series = self._wrapped.get_ohlcv(symbol, timeframe, count)
        report = self._validate_series(series, timeframe)
        self.last_report = report
        if any(issue.startswith("CRITICAL") for issue in report.issues):
            raise DataQualityError("; ".join(report.issues))
        return series

    def get_ticks(self, symbol: Symbol, start: datetime, end: datetime) -> list[Tick]:
        ticks = self._wrapped.get_ticks(symbol, start, end)
        self._validate_ticks(ticks, symbol)
        return ticks

    def get_latest_tick(self, symbol: Symbol) -> Tick:
        tick = self._wrapped.get_latest_tick(symbol)
        self._validate_ticks([tick], symbol)
        return tick

    # -- checks -----------------------------------------------------------

    def _validate_series(self, series: CandleSeries, timeframe: Timeframe) -> ValidationReport:
        report = ValidationReport()
        candles = series.candles

        if not candles:
            report.add("CRITICAL: missing data — empty candle series")
            return report

        seen_timestamps: set[datetime] = set()
        prev: Candle | None = None
        expected_step_seconds = timeframe.minutes * 60

        for candle in candles:
            # Timezone: every timestamp must be timezone-aware UTC.
            if candle.timestamp.tzinfo is None:
                report.add(f"CRITICAL: naive timestamp without timezone at {candle.timestamp}")
                continue
            if candle.timestamp.utcoffset() != timezone.utc.utcoffset(None):
                report.add(f"timestamp not normalized to UTC at {candle.timestamp}")

            # Duplicate timestamps.
            if candle.timestamp in seen_timestamps:
                report.add(f"duplicate timestamp at {candle.timestamp}")
            seen_timestamps.add(candle.timestamp)

            # Invalid OHLC relationships.
            if candle.high < candle.low:
                report.add(f"CRITICAL: high < low at {candle.timestamp}")
            if not (candle.low <= candle.open <= candle.high):
                report.add(f"open outside [low, high] at {candle.timestamp}")
            if not (candle.low <= candle.close <= candle.high):
                report.add(f"close outside [low, high] at {candle.timestamp}")

            # Spread sanity.
            max_spread = self._max_spread_by_symbol.get(series.symbol.name)
            if candle.spread is not None:
                if candle.spread < 0:
                    report.add(f"CRITICAL: negative spread at {candle.timestamp}")
                elif max_spread is not None and candle.spread > max_spread:
                    report.add(f"spread {candle.spread} exceeds max {max_spread} at {candle.timestamp}")

            # Ordering.
            if prev is not None and candle.timestamp < prev.timestamp:
                report.add(f"CRITICAL: out-of-order candle at {candle.timestamp}")

            # Gaps.
            if prev is not None and candle.timestamp > prev.timestamp:
                delta = (candle.timestamp - prev.timestamp).total_seconds()
                if delta > expected_step_seconds * 1.5:
                    report.gaps.append((prev.timestamp, candle.timestamp))

            prev = candle

        return report

    def _validate_ticks(self, ticks: list[Tick], symbol: Symbol) -> None:
        max_spread = self._max_spread_by_symbol.get(symbol.name)
        for tick in ticks:
            if tick.ask < tick.bid:
                raise DataQualityError(f"CRITICAL: ask < bid at {tick.timestamp}")
            if max_spread is not None and tick.spread > max_spread:
                raise DataQualityError(
                    f"CRITICAL: tick spread {tick.spread} exceeds max {max_spread} at {tick.timestamp}"
                )
