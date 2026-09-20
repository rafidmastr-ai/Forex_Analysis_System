"""User-entered capital configuration.

Deliberately separate from AccountState (core/risk/account_state.py). The
user's capital figure is never assumed to equal an MT5 account balance —
even when MT5 is connected for market data, sizing uses this manual value
unless a future capital_basis explicitly opts into MT5_ACCOUNT.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UserCapitalConfig:
    capital_amount: float
    currency: str
    risk_percent: float
