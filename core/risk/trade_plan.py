"""TradePlan — sizing and money figures layered on top of a SelectedSetup.

TradePlan never changes entry/SL/TP levels — those are technical outputs
of the strategy layer. It only decides lot size and translates price
distances into currency amounts.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.signals.selected_setup import SelectedSetup


class LotSource(str, Enum):
    AUTO = "AUTO"
    MANUAL = "MANUAL"


class CapitalSource(str, Enum):
    MANUAL_CAPITAL = "MANUAL_CAPITAL"
    NONE = "NONE"


@dataclass
class TradePlan:
    setup_ref: SelectedSetup
    lot_size: float | None
    lot_source: LotSource
    capital_basis: CapitalSource
    risk_amount: float | None
    expected_profit_tp1: float | None
    expected_profit_tp2: float | None
    expected_loss: float | None
    risk_percent_of_capital: float | None = None
    financial_values_available: bool = False
    financial_disclaimer: str | None = None
