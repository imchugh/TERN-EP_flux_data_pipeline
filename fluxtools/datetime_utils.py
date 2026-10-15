#!/usr/bin/env python3
"""Current/local-time, UTC-offset and timestamp-formatting helpers."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fluxcore.infrastructure.datetime_utils import get_standard_timezone


def get_utc_now(as_iso=False) -> datetime | str:
    """Return the current UTC time, as a datetime or an ISO8601 string."""
    now = datetime.now(UTC)
    if not as_iso:
        return now
    return now.isoformat()


def get_tz_aware_datetime(naive_dt, tz_name, as_iso=False):
    """Attach `tz_name`'s standard-time offset to a naive datetime.

    Args:
        naive_dt: datetime to convert (its own tzinfo, if any, is used as
            the source zone for the conversion — see `datetime.astimezone`).
        tz_name: IANA timezone name (e.g. 'Australia/Darwin').
        as_iso: if True, return an ISO8601 string instead of a datetime.

    Returns:
        Timezone-aware datetime, or its ISO8601 string form if `as_iso`.
    """
    tz_dt = naive_dt.astimezone(get_standard_timezone(tz_name=tz_name))
    if not as_iso:
        return tz_dt
    return tz_dt.isoformat()


def get_local_datetime_now(tz_name, return_tz_aware: bool = True, as_iso: bool = False):
    """Return the current time converted to `tz_name`'s standard-time offset.

    Args:
        tz_name: IANA timezone name (e.g. 'Australia/Darwin').
        return_tz_aware: if False, strip tzinfo from the result.
        as_iso: if True, return an ISO8601 string instead of a datetime.

    Returns:
        Local datetime (aware or naive per `return_tz_aware`), or its
        ISO8601 string form if `as_iso`.
    """
    local = get_tz_aware_datetime(naive_dt=get_utc_now(), tz_name=tz_name)
    if not return_tz_aware:
        local = local.replace(tzinfo=None)
    if not as_iso:
        return local
    return local.isoformat()


def get_UTC_offset(
    tz_name: str,
    date: datetime = None,
    offset_as_delta: bool = False,
    dst: bool = False,
) -> float | timedelta | None:
    """Return `tz_name`'s UTC offset at `date`.

    Args:
        tz_name: IANA timezone name (e.g. 'Australia/Darwin').
        date: datetime to evaluate the offset at (DST varies by date).
            Defaults to now.
        offset_as_delta: if True, return a timedelta instead of hours.
        dst: if True, include any daylight-saving adjustment; if False
            (default), subtract it out to get the standard-time offset.

    Returns:
        UTC offset in hours (or as a timedelta if `offset_as_delta`), or
        None if the timezone has no defined offset at `date`.
    """
    if date is None:
        date = datetime.now()
    tz = ZoneInfo(tz_name)
    offset = tz.utcoffset(date)
    if not dst:
        offset -= tz.dst(date)
    if offset_as_delta:
        return offset
    return offset.total_seconds() / 3600 if offset else None


def format_fast_timestamp(ts: datetime) -> str:
    """Format a sub-second datetime as a Campbell TOA5 timestamp string.

    Truncates to tenths of a second after adding 0.5 ms, so float jitter just
    below a tenth (e.g. 00:00:00.0999996) lands on it rather than the tenth
    before; it is not rounding to the nearest 100 ms. Appends the tenths only
    when non-zero (e.g. '2025-01-01 00:00:00.1'). Use for high-frequency data
    where DATA_TIME_FORMAT would lose sub-second precision.

    Args:
        ts: datetime, typically a pandas Timestamp from a high-frequency index.

    Returns:
        Formatted string compatible with the Campbell TOA5 timestamp column.
    """
    rounded = ts + timedelta(microseconds=500)
    tenths = rounded.microsecond // 100_000
    if tenths == 0:
        return f"{rounded:%Y-%m-%d %H:%M:%S}"
    return f"{rounded:%Y-%m-%d %H:%M:%S}.{tenths}"


def floor_to_interval(dt: datetime, interval_minutes: int) -> datetime:
    """Round dt down to the most recent interval_minutes boundary since midnight.

    E.g. floor_to_interval(2026-08-25T12:06:08, 30) -> 2026-08-25T12:00:00.
    """
    minutes_since_midnight = dt.hour * 60 + dt.minute
    floored_minutes = (minutes_since_midnight // interval_minutes) * interval_minutes
    return dt.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
        minutes=floored_minutes
    )
