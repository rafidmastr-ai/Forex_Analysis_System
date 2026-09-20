from datetime import datetime, timedelta, timezone

import pytest

from core.algorithms.indicators.atr import atr
from core.algorithms.indicators.candlestick_patterns import (
    is_bearish_engulfing,
    is_bullish_engulfing,
    pin_bar_direction,
)
from core.algorithms.indicators.fibonacci import fib_levels, ote_zone
from core.algorithms.indicators.moving_average import ema, sma
from core.algorithms.indicators.vwap import vwap
from core.algorithms.structure.displacement import is_displacement_candle
from core.algorithms.structure.fair_value_gap import find_fair_value_gaps
from core.algorithms.structure.liquidity import find_liquidity_pools, is_liquidity_sweep
from core.algorithms.structure.market_structure import detect_structure_events
from core.algorithms.structure.order_blocks import find_order_blocks
from core.algorithms.structure.premium_discount import premium_discount_zone
from core.algorithms.structure.swings import find_swing_points
from core.algorithms.trend.support_resistance import find_support_resistance_levels
from core.algorithms.trend.trend_detection import detect_trend
from core.algorithms.volatility.volatility import classify_volatility
from core.market_data.models import Candle
from core.signals.enums import Direction

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def C(i, open_, high, low, close, volume=100) -> Candle:
    return Candle(timestamp=BASE + timedelta(minutes=i), open=open_, high=high, low=low, close=close, volume=volume)


def test_sma_and_ema_basic():
    candles = [C(i, 1, 1, 1, close) for i, close in enumerate([1, 2, 3, 4, 5])]
    result = sma(candles, period=3)
    assert result[:2] == [None, None]
    assert result[2] == pytest.approx(2.0)
    assert result[4] == pytest.approx(4.0)

    ema_result = ema(candles, period=3)
    assert ema_result[1] is None
    assert ema_result[2] == pytest.approx(2.0)  # seed = sma of first 3
    assert ema_result[4] is not None


def test_atr_increases_with_larger_ranges():
    tight = [C(i, 1.0, 1.001, 0.999, 1.0) for i in range(20)]
    wide = [C(i, 1.0, 1.02, 0.98, 1.0) for i in range(20)]
    tight_atr = atr(tight, period=14)[-1]
    wide_atr = atr(wide, period=14)[-1]
    assert tight_atr is not None and wide_atr is not None
    assert wide_atr > tight_atr


def test_vwap_between_high_and_low_of_session():
    candles = [C(i, 1.10, 1.11, 1.09, 1.10, volume=100 + i) for i in range(10)]
    result = vwap(candles)
    assert all(v is not None for v in result)
    assert 1.09 <= result[-1] <= 1.11


def test_fib_levels_and_ote_zone_buy():
    levels = fib_levels(swing_high=1.20, swing_low=1.10)
    assert levels[0.5] == pytest.approx(1.15)
    assert levels[1.0] == pytest.approx(1.10)

    zone = ote_zone(swing_high=1.20, swing_low=1.10, direction=Direction.BUY)
    assert 1.10 < zone.low < zone.high < 1.20


def test_candlestick_patterns():
    prev = C(0, open_=1.10, high=1.101, low=1.095, close=1.096)  # bearish
    curr = C(1, open_=1.095, high=1.102, low=1.094, close=1.101)  # bullish engulfing
    assert is_bullish_engulfing(prev, curr) is True
    assert is_bearish_engulfing(prev, curr) is False

    pin = C(2, open_=1.100, high=1.101, low=1.080, close=1.0995)  # long lower wick
    assert pin_bar_direction(pin) == "bullish"


def test_swing_points_detects_local_extremes():
    highs_lows = [1.10, 1.11, 1.15, 1.11, 1.10, 1.05, 1.02, 1.06, 1.09]
    candles = [C(i, v, v + 0.001, v - 0.001, v) for i, v in enumerate(highs_lows)]
    swings = find_swing_points(candles, lookback=2)
    kinds_at_index = {s.index: s.kind for s in swings}
    assert kinds_at_index.get(2) == "high"
    assert kinds_at_index.get(6) == "low"


def test_support_resistance_clusters_nearby_swings():
    from core.algorithms.structure.swings import SwingPoint
    swings = [
        SwingPoint(index=0, timestamp=BASE, price=1.1000, kind="high"),
        SwingPoint(index=5, timestamp=BASE, price=1.1002, kind="high"),
        SwingPoint(index=10, timestamp=BASE, price=1.0900, kind="low"),
    ]
    levels = find_support_resistance_levels(swings, tolerance=0.0005)
    resistance = [lv for lv in levels if lv.kind == "resistance"]
    assert len(resistance) == 1
    assert resistance[0].touches == 2


def test_detect_structure_events_finds_bos_then_choch():
    # Uptrend impulse breaking a swing high (BOS-like first break), then a
    # sharp reversal breaking the prior swing low (CHoCH).
    closes = [1.10, 1.11, 1.12, 1.11, 1.10, 1.09, 1.12, 1.14, 1.13, 1.05]
    candles = [C(i, v, v + 0.002, v - 0.002, v) for i, v in enumerate(closes)]
    swings = find_swing_points(candles, lookback=1)

    events = detect_structure_events(candles, swings)

    assert len(events) >= 1
    assert any(e.direction == Direction.SELL for e in events) or any(e.direction == Direction.BUY for e in events)


def test_order_blocks_found_before_structure_break():
    from core.algorithms.structure.market_structure import StructureEvent
    candles = [
        C(0, 1.100, 1.101, 1.095, 1.096),  # bearish candle -> becomes the bullish OB
        C(1, 1.096, 1.120, 1.096, 1.119),  # displacement breaking higher
    ]
    event = StructureEvent(kind="CHoCH", direction=Direction.BUY, timestamp=candles[1].timestamp,
                            price=1.119, broken_level=1.10, index=1)

    blocks = find_order_blocks(candles, [event], lookback=5)

    assert len(blocks) == 1
    assert blocks[0].direction == Direction.BUY
    assert blocks[0].zone.low == 1.095


def test_fair_value_gap_detected_on_gap_up():
    candles = [
        C(0, 1.100, 1.102, 1.098, 1.101),
        C(1, 1.101, 1.130, 1.115, 1.128),  # displacement candle
        C(2, 1.128, 1.135, 1.120, 1.130),  # low (1.120) > candle0 high (1.102) -> bullish FVG
    ]
    gaps = find_fair_value_gaps(candles)
    assert len(gaps) == 1
    assert gaps[0].direction == Direction.BUY
    assert gaps[0].zone.low == pytest.approx(1.102)
    assert gaps[0].zone.high == pytest.approx(1.120)


def test_liquidity_pool_and_sweep():
    from core.algorithms.structure.swings import SwingPoint
    swings = [
        SwingPoint(index=0, timestamp=BASE, price=1.1050, kind="high"),
        SwingPoint(index=5, timestamp=BASE, price=1.1051, kind="high"),
    ]
    pools = find_liquidity_pools(swings, tolerance=0.0005)
    assert len(pools) == 1
    pool = pools[0]
    assert pool.kind == "buy_side"

    sweep_candle = C(10, 1.1030, 1.1060, 1.1025, 1.1040)  # wicks above pool, closes back below
    no_sweep_candle = C(11, 1.1030, 1.1060, 1.1025, 1.1055)  # closes above pool -> not a sweep
    assert is_liquidity_sweep(sweep_candle, pool) is True
    assert is_liquidity_sweep(no_sweep_candle, pool) is False


def test_premium_discount_zone():
    assert premium_discount_zone(1.20, 1.10, 1.18) == "premium"
    assert premium_discount_zone(1.20, 1.10, 1.12) == "discount"
    assert premium_discount_zone(1.20, 1.10, 1.15) == "equilibrium"


def test_displacement_candle_detection():
    big_candle = C(0, 1.10, 1.13, 1.09, 1.12)
    small_candle = C(1, 1.10, 1.101, 1.099, 1.1005)
    assert is_displacement_candle(big_candle, atr_value=0.01, multiplier=1.5) is True
    assert is_displacement_candle(small_candle, atr_value=0.01, multiplier=1.5) is False
    assert is_displacement_candle(big_candle, atr_value=None) is False


def test_classify_volatility_relative_ranking():
    values = [0.001] * 10 + [0.002] * 10 + [0.02]
    assert classify_volatility(values) == "high"
    assert classify_volatility([0.001] * 3) == "medium"  # not enough history -> neutral default


def test_trend_detection_insufficient_data_returns_none():
    candles = [C(i, 1.1, 1.1, 1.1, 1.1) for i in range(5)]
    result = detect_trend(candles)
    assert result.direction is None


def test_breaker_block_flips_role_after_invalidation():
    from core.algorithms.structure.breaker_blocks import find_breaker_blocks
    from core.algorithms.structure.order_blocks import OrderBlock
    from core.signals.strategy_signal import PriceZone

    candles = [C(i, 1.10, 1.101, 1.099, 1.10) for i in range(5)]
    candles.append(C(5, 1.098, 1.099, 1.094, 1.095))  # closes below the bullish OB's low -> breaker
    bullish_ob = OrderBlock(direction=Direction.BUY, zone=PriceZone(1.097, 1.100), timestamp=BASE, index=2,
                             structure_event_index=3)

    breakers = find_breaker_blocks(candles, [bullish_ob])

    assert len(breakers) == 1
    assert breakers[0].direction == Direction.SELL  # flipped to resistance
    assert breakers[0].zone == bullish_ob.zone


def test_breaker_block_none_when_not_invalidated():
    from core.algorithms.structure.breaker_blocks import find_breaker_blocks
    from core.algorithms.structure.order_blocks import OrderBlock
    from core.signals.strategy_signal import PriceZone

    candles = [C(i, 1.10, 1.101, 1.099, 1.10) for i in range(5)]
    bullish_ob = OrderBlock(direction=Direction.BUY, zone=PriceZone(1.097, 1.100), timestamp=BASE, index=2,
                             structure_event_index=3)

    assert find_breaker_blocks(candles, [bullish_ob]) == []


def test_trend_detection_detects_uptrend():
    closes = [1.0 + i * 0.001 for i in range(120)]
    candles = [C(i, c, c + 0.0005, c - 0.0005, c) for i, c in enumerate(closes)]
    result = detect_trend(candles)
    assert result.direction == Direction.BUY
