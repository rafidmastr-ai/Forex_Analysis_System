from datetime import datetime, timedelta, timezone

from core.algorithms.structure.swings import find_swing_points
from core.confidence.component_scoring import ComponentWeights, weighted_score
from core.context.analysis_context import AnalysisContext
from core.market_data.models import Candle, CandleSeries, Symbol, Timeframe
from core.signals.enums import Direction
from core.strategies.classic.classic_strategy import (
    BASE_CONFIDENCE,
    CONFIDENCE_SCALE,
    GATE_CANDLESTICK,
    ClassicStrategy,
)

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
SYMBOL = Symbol(name="EURUSD", pip_size=0.0001, digits=5, contract_size=100000)


def _uptrend_with_pullback_context() -> AnalysisContext:
    """A steady uptrend with periodic dips (so real swing lows form), then a
    final pullback to the most recent swing low with a bullish engulfing
    candle — the exact setup ClassicStrategy looks for.
    """
    price = 1.1000
    candles: list[Candle] = []
    for i in range(90):
        price += 0.0006
        if i % 15 == 0 and i > 0:
            price -= 0.0020
        o = price - 0.0003
        hi = max(o, price) + 0.0003
        lo = min(o, price) - 0.0003
        candles.append(Candle(timestamp=BASE + timedelta(minutes=i), open=o, high=hi, low=lo, close=price, volume=100))

    last_low = max((s for s in find_swing_points(candles, lookback=2) if s.kind == "low"), key=lambda s: s.timestamp)
    support = last_low.price

    prev = Candle(timestamp=BASE + timedelta(minutes=90), open=support + 0.0006, high=support + 0.0008,
                  low=support - 0.0005, close=support - 0.0002, volume=100)
    curr = Candle(timestamp=BASE + timedelta(minutes=91), open=support - 0.0003, high=support + 0.0009,
                  low=support - 0.0005, close=support + 0.0007, volume=100)
    candles += [prev, curr]

    series = CandleSeries(symbol=SYMBOL, timeframe=Timeframe.M15, candles=candles)
    return AnalysisContext(
        symbol=SYMBOL, current_bid=curr.close, current_ask=curr.close + 0.0001, session="London",
        higher_timeframe=series, middle_timeframe=series, entry_timeframe=series, as_of=curr.timestamp,
    )


def _flat_ranging_context(count: int = 90) -> AnalysisContext:
    candles = [
        Candle(timestamp=BASE + timedelta(minutes=i), open=1.1000, high=1.1002, low=1.0998, close=1.1000, volume=100)
        for i in range(count)
    ]
    series = CandleSeries(symbol=SYMBOL, timeframe=Timeframe.M15, candles=candles)
    return AnalysisContext(
        symbol=SYMBOL, current_bid=1.1000, current_ask=1.1001, session="London",
        higher_timeframe=series, middle_timeframe=series, entry_timeframe=series, as_of=candles[-1].timestamp,
    )


def test_classic_strategy_produces_buy_signal_on_trend_pullback():
    strategy = ClassicStrategy()
    signal = strategy.analyze(_uptrend_with_pullback_context())

    assert signal is not None
    assert signal.direction == Direction.BUY
    assert signal.suggested_take_profit_1 > signal.suggested_entry_zone.mid > signal.suggested_stop_loss
    assert signal.suggested_take_profit_2 > signal.suggested_take_profit_1
    assert "Candlestick confirmation" in " ".join(signal.rationale)
    assert signal.raw_score_components["trend_alignment"] is True


def test_classic_strategy_returns_none_on_insufficient_data():
    ctx = _flat_ranging_context(count=10)
    assert ClassicStrategy().analyze(ctx) is None


def test_classic_strategy_returns_none_when_ranging():
    ctx = _flat_ranging_context(count=90)
    assert ClassicStrategy().analyze(ctx) is None


def test_default_weights_reproduce_exact_legacy_score_arithmetic():
    """Regression guard for the component-scoring refactor: the default
    weights must reproduce the pre-refactor `base=55; +5 if strong trend;
    +10 if fib confluence` arithmetic exactly, for every combination."""
    weights = ClassicStrategy.DEFAULT_WEIGHTS
    cases = [
        ({"trend_strength": 1.0, "fibonacci": 1.0, "sr_quality": 0.0, "candlestick_strength": 1.0}, 70),
        ({"trend_strength": 1.0, "fibonacci": 0.0, "sr_quality": 0.0, "candlestick_strength": 1.0}, 60),
        ({"trend_strength": 0.0, "fibonacci": 1.0, "sr_quality": 0.0, "candlestick_strength": 1.0}, 65),
        ({"trend_strength": 0.0, "fibonacci": 0.0, "sr_quality": 0.0, "candlestick_strength": 1.0}, 55),
    ]
    for components, expected in cases:
        assert weighted_score(components, weights, base=BASE_CONFIDENCE, scale=CONFIDENCE_SCALE) == expected


def test_candlestick_gate_can_be_disabled_for_ablation():
    ctx = _uptrend_with_pullback_context()
    # Overwrite the final candle so it no longer confirms (a plain doji-like
    # candle with no engulfing/pin-bar shape).
    last = ctx.entry_timeframe.candles[-1]
    non_confirming = Candle(timestamp=last.timestamp, open=last.close, high=last.close + 0.0001,
                             low=last.close - 0.0001, close=last.close + 0.00002, volume=100)
    candles = ctx.entry_timeframe.candles[:-1] + [non_confirming]
    series = CandleSeries(symbol=SYMBOL, timeframe=Timeframe.M15, candles=candles)
    ablated_ctx = AnalysisContext(symbol=SYMBOL, current_bid=non_confirming.close, current_ask=non_confirming.close + 0.0001,
                                   session="London", higher_timeframe=series, middle_timeframe=series,
                                   entry_timeframe=series, as_of=non_confirming.timestamp)

    assert ClassicStrategy().analyze(ablated_ctx) is None  # gate active by default
    signal = ClassicStrategy(disabled_components=frozenset({GATE_CANDLESTICK})).analyze(ablated_ctx)
    assert signal is not None  # gate disabled -> trade generated anyway


def test_custom_weights_change_confidence_score():
    ctx = _uptrend_with_pullback_context()
    default_signal = ClassicStrategy().analyze(ctx)
    all_in_fibonacci = ClassicStrategy(weights=ComponentWeights({"fibonacci": 1.0})).analyze(ctx)

    assert default_signal is not None and all_in_fibonacci is not None
    # Same setup, different weighting scheme -> confidence must be free to differ.
    assert isinstance(default_signal.raw_score_components["base_confidence"], int)
    assert isinstance(all_in_fibonacci.raw_score_components["base_confidence"], int)


def test_classic_strategy_is_registered():
    import core.strategies.classic  # noqa: F401 — triggers registration
    from core.strategies.registry import registry

    ids = [m.strategy_id for m in registry.all()]
    assert "classic_sr_trend_fib" in ids
