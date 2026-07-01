"""Tests for the timezone helpers."""

from datetime import datetime, timezone

from services.timeutil import get_tz, now, parse_dt


def test_now_is_timezone_aware():
    assert now().tzinfo is not None


def test_parse_naive_assumes_configured_zone():
    # A naive value is interpreted in the configured zone, so it equals the same
    # wall-clock time constructed with that zone.
    dt = parse_dt("2026-07-01T14:00:00")
    assert dt == datetime(2026, 7, 1, 14, 0, tzinfo=get_tz())


def test_parse_offset_is_preserved():
    dt = parse_dt("2026-07-01T14:00:00+00:00")
    assert dt == datetime(2026, 7, 1, 14, 0, tzinfo=timezone.utc)


def test_parse_z_suffix_is_utc():
    dt = parse_dt("2026-07-01T14:00:00Z")
    assert dt == datetime(2026, 7, 1, 14, 0, tzinfo=timezone.utc)


def test_parse_tolerates_space_separator():
    dt = parse_dt("2026-07-01 14:00:00")
    assert (dt.year, dt.month, dt.day, dt.hour) == (2026, 7, 1, 14)
    assert dt.tzinfo is not None
