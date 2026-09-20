"""ICT Kill Zones — time windows of higher institutional participation.

Defined in New York local time (the standard ICT reference), converted
from each candle's UTC timestamp via zoneinfo, which applies the correct
EST/EDT offset for that date automatically. This means Daylight Saving
Time is handled correctly without any manual offset math, and the zones
are NOT relative to wherever the user/server happens to be — "the user's
timezone" is never used as a stand-in for a global market reference.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

NY_TZ = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class KillZone:
    name: str
    start: time  # New York local time
    end: time


DEFAULT_KILL_ZONES: tuple[KillZone, ...] = (
    KillZone("Asian", time(20, 0), time(0, 0)),
    KillZone("London Open", time(2, 0), time(5, 0)),
    KillZone("New York Open", time(7, 0), time(10, 0)),
    KillZone("London Close", time(10, 0), time(12, 0)),
)


def active_kill_zone(utc_timestamp: datetime, zones: tuple[KillZone, ...] = DEFAULT_KILL_ZONES) -> str | None:
    if utc_timestamp.tzinfo is None:
        raise ValueError("active_kill_zone requires a timezone-aware UTC datetime")
    local_time = utc_timestamp.astimezone(NY_TZ).time()
    for zone in zones:
        if zone.start <= zone.end:
            if zone.start <= local_time <= zone.end:
                return zone.name
        else:  # window wraps past midnight (e.g. Asian session)
            if local_time >= zone.start or local_time <= zone.end:
                return zone.name
    return None
