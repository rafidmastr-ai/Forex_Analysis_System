"""Kill zones are defined in New York local time and must shift correctly
between EST and EDT — proving DST is actually handled, not assumed away.
"""
from datetime import datetime, timezone

from core.algorithms.session.kill_zones import active_kill_zone


def test_same_utc_instant_resolves_differently_across_dst():
    winter_utc = datetime(2026, 1, 15, 11, 30, tzinfo=timezone.utc)  # EST: 06:30 local -> gap, no zone
    summer_utc = datetime(2026, 7, 15, 11, 30, tzinfo=timezone.utc)  # EDT: 07:30 local -> New York Open

    assert active_kill_zone(winter_utc) is None
    assert active_kill_zone(summer_utc) == "New York Open"


def test_new_york_open_in_winter():
    # 07:00-10:00 EST == 12:00-15:00 UTC in January.
    dt = datetime(2026, 1, 15, 13, 0, tzinfo=timezone.utc)
    assert active_kill_zone(dt) == "New York Open"


def test_london_open_zone():
    # 02:00-05:00 EST == 07:00-10:00 UTC in January.
    dt = datetime(2026, 1, 15, 8, 0, tzinfo=timezone.utc)
    assert active_kill_zone(dt) == "London Open"


def test_asian_session_wraps_past_midnight():
    # 23:30 EST on Jan 15 == 04:30 UTC on Jan 16.
    dt = datetime(2026, 1, 16, 4, 30, tzinfo=timezone.utc)
    assert active_kill_zone(dt) == "Asian"


def test_outside_any_kill_zone_returns_none():
    dt = datetime(2026, 1, 15, 20, 0, tzinfo=timezone.utc)  # 15:00 EST — well after London Close, before Asian
    assert active_kill_zone(dt) is None


def test_naive_timestamp_raises():
    import pytest
    with pytest.raises(ValueError):
        active_kill_zone(datetime(2026, 1, 15, 12, 0))
