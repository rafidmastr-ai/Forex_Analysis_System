from datetime import datetime, timedelta, timezone

from core.context.timeframe_selector import TimeframeSelector, classify_volatility_from_candles
from core.market_data.models import Candle, Timeframe

CONFIG = {
    "default_mapping": {"higher": "H4", "middle": "H1", "entry": "M15"},
    "selection_rules": [{"condition": "high_volatility", "entry": "M5"}],
}


def test_default_mapping_used_without_volatility_override():
    selector = TimeframeSelector(CONFIG)
    result = selector.select(volatility="low")
    assert result.higher == Timeframe.H4
    assert result.middle == Timeframe.H1
    assert result.entry == Timeframe.M15


def test_high_volatility_rule_overrides_entry_timeframe():
    selector = TimeframeSelector(CONFIG)
    result = selector.select(volatility="high")
    assert result.entry == Timeframe.M5
    assert result.higher == Timeframe.H4  # rule only overrides entry here


def test_no_volatility_argument_falls_back_to_default():
    selector = TimeframeSelector(CONFIG)
    result = selector.select()
    assert result.entry == Timeframe.M15


def test_classify_volatility_from_candles_smoke():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = [
        Candle(timestamp=base + timedelta(minutes=i), open=1.1, high=1.1 + 0.0001 * (i % 3),
               low=1.1 - 0.0001 * (i % 3), close=1.1, volume=100)
        for i in range(30)
    ]
    result = classify_volatility_from_candles(candles)
    assert result in ("low", "medium", "high")
