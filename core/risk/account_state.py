"""AccountState — reflects a real broker account (e.g. via MT5), when one
is connected. Kept fully separate from UserCapitalConfig by design.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AccountState:
    balance: float
    equity: float
    margin: float
    currency: str
