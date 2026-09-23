"""TimeframeSelector — resolves Higher/Middle/Entry timeframes internally.

The user never picks a timeframe. This component decides it, driven by
config.timeframes (default_mapping + selection_rules) and, when a rule
calls for it, the symbol's current volatility regime. Callers do a small
first pass to classify volatility (see backend/routers/signals.py and
backtesting/engine.py for the two call sites), then call select() to get
the final timeframes before fetching the full-lookback data.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.algorithms.indicators.atr import atr
from core.algorithms.volatility.volatility import classify_volatility
from core.market_data.models import Candle, Timeframe


def classify_volatility_from_candles(candles: list[Candle]) -> str:
    """Shared by the live /analyze flow and the Backtesting Engine so both
    pick timeframes the same way, from an ATR-relative volatility read."""
    return classify_volatility(atr(candles, period=14))


@dataclass(frozen=True)
class SelectedTimeframes:
    higher: Timeframe
    middle: Timeframe
    entry: Timeframe


class TimeframeSelector:
    def __init__(self, timeframes_config: dict):
        self._default = timeframes_config["default_mapping"]
        self._rules = timeframes_config.get("selection_rules", [])
        # Optional, additive: a per-entry-timeframe Higher/Middle table (config's
        # `timeframes.entry_mapping`) used only by resolve_for_entry() below. Absent
        # from settings.dev/prod/windows.yaml (live /analyze always calls select(),
        # never resolve_for_entry()) -- this never changes select()'s behavior.
        self._entry_mapping = timeframes_config.get("entry_mapping")

    def select(self, volatility: str | None = None) -> SelectedTimeframes:
        higher = Timeframe(self._default["higher"])
        middle = Timeframe(self._default["middle"])
        entry = Timeframe(self._default["entry"])

        for rule in self._rules:
            if rule.get("condition") == "high_volatility" and volatility == "high":
                if "higher" in rule:
                    higher = Timeframe(rule["higher"])
                if "middle" in rule:
                    middle = Timeframe(rule["middle"])
                if "entry" in rule:
                    entry = Timeframe(rule["entry"])

        return SelectedTimeframes(higher=higher, middle=middle, entry=entry)

    def resolve_for_entry(self, entry: Timeframe) -> SelectedTimeframes:
        """Higher/Middle for a CALLER-CHOSEN entry timeframe, from config's
        `timeframes.entry_mapping` table -- for the Backtesting Engine, which
        (unlike live /analyze) tests entry timeframes other than whatever
        `default_mapping`/`selection_rules` alone would pick, and needs a
        Higher/Middle pair that is actually coarser than (or, where the
        available timeframe set makes that impossible, no finer than) that
        entry, not the single static H4/H1 pair regardless of entry.

        Never called by live /analyze (see backend/routers/signals.py, which
        only ever calls select()) -- adding this changes no production
        behavior; it exists purely so the Backtesting Engine can be correct
        across every entry timeframe it tests.
        """
        if not self._entry_mapping:
            raise ValueError(
                "resolve_for_entry() requires config.timeframes.entry_mapping -- "
                "none was supplied (this timeframes_config has no 'entry_mapping' key)."
            )
        row = self._entry_mapping.get(entry.value)
        if row is None:
            raise ValueError(
                f"no entry_mapping row for entry timeframe {entry.value!r} -- "
                f"configured entries are {sorted(self._entry_mapping)}."
            )
        return SelectedTimeframes(higher=Timeframe(row["higher"]), middle=Timeframe(row["middle"]), entry=entry)
