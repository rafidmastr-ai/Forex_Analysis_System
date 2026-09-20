"""Volatility classification from ATR, relative to its own recent history
— avoids hardcoding an absolute ATR threshold per symbol."""
from __future__ import annotations


def classify_volatility(atr_values: list[float | None], lookback: int = 50) -> str:
    """Returns 'low' | 'medium' | 'high' based on where the latest ATR sits
    within its own recent distribution (percentile-style, dependency-free).
    """
    clean = [v for v in atr_values[-lookback:] if v is not None]
    if len(clean) < 5:
        return "medium"
    current = clean[-1]
    sorted_values = sorted(clean)
    rank = sorted_values.index(current) / (len(sorted_values) - 1)
    if rank < 0.33:
        return "low"
    if rank < 0.66:
        return "medium"
    return "high"
