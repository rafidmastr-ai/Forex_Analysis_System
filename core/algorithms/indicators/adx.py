"""Average Directional Index — trend strength (not direction).

Standard Wilder smoothing. Returns None for indices before the warm-up
period, same convention as atr()/ema().
"""
from __future__ import annotations

from core.algorithms.indicators.atr import true_range
from core.market_data.models import Candle


def adx(candles: list[Candle], period: int = 14) -> list[float | None]:
    n = len(candles)
    result: list[float | None] = [None] * n
    if n < period * 2:
        return result

    plus_dm = [0.0] * n
    minus_dm = [0.0] * n
    tr = [0.0] * n

    for i in range(1, n):
        up_move = candles[i].high - candles[i - 1].high
        down_move = candles[i - 1].low - candles[i].low
        plus_dm[i] = up_move if (up_move > down_move and up_move > 0) else 0.0
        minus_dm[i] = down_move if (down_move > up_move and down_move > 0) else 0.0
        tr[i] = true_range(candles[i], candles[i - 1])

    def wilder_smooth(values: list[float]) -> list[float]:
        smoothed = [0.0] * n
        seed = sum(values[1: period + 1])
        smoothed[period] = seed
        for i in range(period + 1, n):
            smoothed[i] = smoothed[i - 1] - (smoothed[i - 1] / period) + values[i]
        return smoothed

    tr_smooth = wilder_smooth(tr)
    plus_dm_smooth = wilder_smooth(plus_dm)
    minus_dm_smooth = wilder_smooth(minus_dm)

    dx = [0.0] * n
    for i in range(period, n):
        if tr_smooth[i] == 0:
            continue
        plus_di = 100 * plus_dm_smooth[i] / tr_smooth[i]
        minus_di = 100 * minus_dm_smooth[i] / tr_smooth[i]
        denom = plus_di + minus_di
        dx[i] = 100 * abs(plus_di - minus_di) / denom if denom else 0.0

    first_adx_index = period * 2 - 1
    if first_adx_index >= n:
        return result
    seed_adx = sum(dx[period:first_adx_index + 1]) / period
    result[first_adx_index] = seed_adx
    prev = seed_adx
    for i in range(first_adx_index + 1, n):
        prev = (prev * (period - 1) + dx[i]) / period
        result[i] = prev
    return result
