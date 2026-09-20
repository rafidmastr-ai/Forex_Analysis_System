"""Liquidity pools (equal highs/lows where stop orders cluster) and sweep
detection (a wick through the pool that closes back inside — a stop hunt).
"""
from __future__ import annotations

from dataclasses import dataclass

from core.algorithms.structure.swings import SwingPoint
from core.market_data.models import Candle


@dataclass(frozen=True)
class LiquidityPool:
    kind: str  # "buy_side" (resting above equal highs) | "sell_side" (below equal lows)
    price: float
    touches: int


def find_liquidity_pools(swings: list[SwingPoint], tolerance: float, min_touches: int = 2) -> list[LiquidityPool]:
    pools: list[LiquidityPool] = []
    for swing_kind, pool_kind in (("high", "buy_side"), ("low", "sell_side")):
        points = sorted((s.price for s in swings if s.kind == swing_kind))
        clusters: list[list[float]] = []
        for price in points:
            if clusters and abs(price - clusters[-1][-1]) <= tolerance:
                clusters[-1].append(price)
            else:
                clusters.append([price])
        for cluster in clusters:
            if len(cluster) >= min_touches:
                pools.append(LiquidityPool(kind=pool_kind, price=sum(cluster) / len(cluster), touches=len(cluster)))
    return pools


def is_liquidity_sweep(candle: Candle, pool: LiquidityPool) -> bool:
    if pool.kind == "buy_side":
        return candle.high > pool.price and candle.close < pool.price
    return candle.low < pool.price and candle.close > pool.price
