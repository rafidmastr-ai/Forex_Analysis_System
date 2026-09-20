"""Shared vocabulary used across strategies, signals and results.

Kept in one place to avoid import cycles between strategies/, signals/,
confidence/ and risk/.
"""
from __future__ import annotations

from enum import Enum


class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class StrategyCategory(str, Enum):
    CLASSIC = "Classic"
    SMC = "SMC"
    ICT = "ICT"


class ConfidenceLabel(str, Enum):
    WEAK = "Weak"
    MEDIUM = "Medium"
    STRONG = "Strong"


class SetupStatus(str, Enum):
    SELECTED = "SELECTED"
    REJECTED_ALTERNATIVE = "REJECTED_ALTERNATIVE"
    REJECTED_MIN_RR = "REJECTED_MIN_RR"
