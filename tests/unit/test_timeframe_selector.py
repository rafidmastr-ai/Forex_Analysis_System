from datetime import datetime, timedelta, timezone

import pytest

from core.context.timeframe_selector import TimeframeSelector, classify_volatility_from_candles
from core.market_data.models import Candle, Timeframe

CONFIG = {
    "default_mapping": {"higher": "H4", "middle": "H1", "entry": "M15"},
    "selection_rules": [{"condition": "high_volatility", "entry": "M5"}],
}

ENTRY_MAPPING_CONFIG = {
    **CONFIG,
    "entry_mapping": {
        "M1": {"higher": "M15", "middle": "M5"},
        "M5": {"higher": "H1", "middle": "M15"},
        "M15": {"higher": "H4", "middle": "H1"},
        "M30": {"higher": "H4", "middle": "H1"},
        "H1": {"higher": "H4", "middle": "H1"},
        "H4": {"higher": "H4", "middle": "H4"},
    },
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


def test_select_is_unaffected_by_entry_mapping_presence():
    """Live /analyze only ever calls select() -- adding entry_mapping to the
    config must not change its behavior at all."""
    selector = TimeframeSelector(ENTRY_MAPPING_CONFIG)
    result = selector.select(volatility="low")
    assert result.higher == Timeframe.H4
    assert result.middle == Timeframe.H1
    assert result.entry == Timeframe.M15


@pytest.mark.parametrize(
    "entry, expected_higher, expected_middle",
    [
        (Timeframe.M1, Timeframe.M15, Timeframe.M5),
        (Timeframe.M5, Timeframe.H1, Timeframe.M15),
        (Timeframe.M15, Timeframe.H4, Timeframe.H1),
        (Timeframe.M30, Timeframe.H4, Timeframe.H1),
        (Timeframe.H1, Timeframe.H4, Timeframe.H1),
        (Timeframe.H4, Timeframe.H4, Timeframe.H4),
    ],
)
def test_resolve_for_entry_matches_the_documented_table(entry, expected_higher, expected_middle):
    selector = TimeframeSelector(ENTRY_MAPPING_CONFIG)
    result = selector.resolve_for_entry(entry)
    assert result.entry == entry
    assert result.higher == expected_higher
    assert result.middle == expected_middle


def test_resolve_for_entry_higher_is_never_below_entry():
    selector = TimeframeSelector(ENTRY_MAPPING_CONFIG)
    for entry in (Timeframe.M1, Timeframe.M5, Timeframe.M15, Timeframe.M30, Timeframe.H1, Timeframe.H4):
        result = selector.resolve_for_entry(entry)
        assert result.higher.minutes >= entry.minutes


def test_resolve_for_entry_raises_without_entry_mapping_in_config():
    selector = TimeframeSelector(CONFIG)  # no entry_mapping key
    with pytest.raises(ValueError, match="entry_mapping"):
        selector.resolve_for_entry(Timeframe.M1)


def test_resolve_for_entry_raises_for_unmapped_entry():
    config = {**CONFIG, "entry_mapping": {"M15": {"higher": "H4", "middle": "H1"}}}
    selector = TimeframeSelector(config)
    with pytest.raises(ValueError, match="D1"):
        selector.resolve_for_entry(Timeframe.D1)


def test_classify_volatility_from_candles_smoke():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = [
        Candle(timestamp=base + timedelta(minutes=i), open=1.1, high=1.1 + 0.0001 * (i % 3),
               low=1.1 - 0.0001 * (i % 3), close=1.1, volume=100)
        for i in range(30)
    ]
    result = classify_volatility_from_candles(candles)
    assert result in ("low", "medium", "high")
