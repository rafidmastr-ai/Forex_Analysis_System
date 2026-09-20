"""Premium/Discount zone — where current price sits within the most recent
swing range. SMC/ICT prefer selling from premium and buying from discount.
"""
from __future__ import annotations


def premium_discount_zone(swing_high: float, swing_low: float, current_price: float) -> str:
    if swing_high == swing_low:
        return "equilibrium"
    ratio = (current_price - swing_low) / (swing_high - swing_low)
    eps = 1e-9  # float-precision guard around the exact 50% level
    if ratio > 0.5 + eps:
        return "premium"
    if ratio < 0.5 - eps:
        return "discount"
    return "equilibrium"
