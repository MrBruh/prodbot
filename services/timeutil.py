"""Timezone helpers so reminder times mean the same thing on any server.

The bot must not depend on the host's system clock zone: a reminder for "2pm"
means 2pm in the configured zone (``config.TIMEZONE``), whether the process runs
in UTC, local time, or anywhere else. All reminder scheduling and comparison go
through here.
"""

from datetime import datetime

from config import TIMEZONE

try:  # Python 3.9+
    from zoneinfo import ZoneInfo
except ImportError:  # Python 3.8
    from backports.zoneinfo import ZoneInfo


def get_tz() -> ZoneInfo:
    """The configured timezone as a tzinfo (ZoneInfo caches instances)."""
    return ZoneInfo(TIMEZONE)


def now() -> datetime:
    """Current time as an aware datetime in the configured zone."""
    return datetime.now(get_tz())


def parse_dt(value: str) -> datetime:
    """Parse an ISO 8601 datetime to an aware datetime in the configured zone.

    Naive inputs are assumed to already be in the configured zone; a trailing
    ``Z`` is accepted as UTC. Tolerant of the ``T``/space date-time separator.
    """
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=get_tz())
    return dt
