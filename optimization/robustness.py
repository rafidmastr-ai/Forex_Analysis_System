"""Robustness (R:R-cap) post-processing over already-computed backtest
outcomes -- see config/robustness_backtest.yaml for the rationale and the
exact cap values used.

This module touches NOTHING upstream of a trade's own outcome: it reads
TradeOutcome.r_multiple (the REALIZED R BacktestEngine already computed --
risk_reward_tp1/tp2 on a win, -1.0 on SL, 0.0 on NONE; see
backtesting/engine.py's TradeOutcome docstring), never
SelectedSetup.risk_reward_tp1/tp2 as a *planned*, signal-time statistic
(that field is unaffected by any cap here, by design -- capping is a
purely descriptive, post-trade transform, not a re-decision). Applying a
cap can only ever produce a NEW TradeOutcome whose r_multiple is smaller
than or equal to the original; `hit`, `opened_at`, `closed_at` and `setup`
(hence Entry/SL/TP) are always identical to the input.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import yaml

from backtesting.engine import TradeOutcome

DEFAULT_CONFIG_PATH = Path("config/robustness_backtest.yaml")


@dataclass(frozen=True)
class RobustnessMode:
    label: str
    rr_cap: float | None  # None = Baseline (no cap, identity transform)


def load_robustness_modes(config_path: Path = DEFAULT_CONFIG_PATH) -> list[RobustnessMode]:
    raw = yaml.safe_load(config_path.read_text())["robustness_backtest"]["modes"]
    return [RobustnessMode(label=m["label"], rr_cap=m["rr_cap"]) for m in raw]


def apply_rr_cap(outcomes: list[TradeOutcome], rr_cap: float | None) -> list[TradeOutcome]:
    """Returns a NEW list of TradeOutcome, each with r_multiple replaced by
    min(r_multiple, rr_cap) -- never the reverse (a cap never raises a
    value). `rr_cap=None` (Baseline) returns the outcomes completely
    unchanged (a fresh list, same TradeOutcome objects, so it is trivially
    identical to never having applied a cap at all).

    Never mutates the input list or its TradeOutcome objects (TradeOutcome
    is a plain, non-frozen dataclass elsewhere in the system, so this is
    deliberate: `dataclasses.replace` always returns a new instance,
    leaving the original outcome -- and therefore every other mode's view
    of the same trade -- untouched).
    """
    if rr_cap is None:
        return list(outcomes)
    return [replace(o, r_multiple=min(o.r_multiple, rr_cap)) for o in outcomes]
