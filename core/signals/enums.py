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
    # Added during the research-driven expansion phase (see research/
    # STRATEGY_RESEARCH_REGISTRY.md) — additive only, nothing above changed
    # meaning, so every existing exhaustive-looking `s.category == X` check
    # (confidence_engine.py, run_config.py) keeps working unmodified.
    LIQUIDITY = "Liquidity"   # sweep/displacement/retracement-style strategies, distinct from SMC's BOS-first entry
    BREAKOUT = "Breakout"     # range/session-breakout-style strategies


class ConfidenceLabel(str, Enum):
    WEAK = "Weak"
    MEDIUM = "Medium"
    STRONG = "Strong"


class SetupStatus(str, Enum):
    SELECTED = "SELECTED"
    REJECTED_ALTERNATIVE = "REJECTED_ALTERNATIVE"
    REJECTED_MIN_RR = "REJECTED_MIN_RR"
