"""Pure helpers for bucketing and reading measurement values."""

import datetime as dt
from decimal import Decimal, InvalidOperation
from typing import Any

from server.aggregation.const import RESOLUTION_MINUTES, Resolution
from server.db.measurements import Measurement
from server.health.util import civil_from, parse_offset, parse_timestamp


def bucket_of(measurement: Measurement, resolution: Resolution) -> dt.datetime | None:
    """The local start of the bucket a measurement falls in.

    A measurement belongs to the bucket its window starts in; it is not split
    across buckets. A daily bucket keys on the stored civil date, and so does a
    full-day activity, which has no local start to floor.
    """
    if resolution is Resolution.DAY or measurement.local_start is None:
        if measurement.civil_date is None:
            return None
        return dt.datetime.combine(measurement.civil_date, dt.time())
    minutes = RESOLUTION_MINUTES[resolution]
    local = measurement.local_start
    since_midnight = local.hour * 60 + local.minute
    floored = since_midnight - since_midnight % minutes
    return dt.datetime.combine(local.date(), dt.time()) + dt.timedelta(minutes=floored)


def number(value: Any) -> float | None:
    """A float from whatever Google sent: a number, a Decimal, or an int64 string."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float | Decimal):
        return float(value)
    if isinstance(value, str):
        try:
            return float(Decimal(value))
        except InvalidOperation:
            return None
    return None


def tidy(value: float) -> int | float:
    """A whole number as an int, so a step count does not render as ``412.0``."""
    return int(value) if value.is_integer() else value


def tidy_or_none(value: float | None) -> int | float | None:
    return None if value is None else tidy(value)


def value_of(row: Measurement) -> float | None:
    """A row's own number, as a category total's contribution."""
    return number(row.value_numeric)


def minutes_of(row: Measurement) -> float:
    """A row's window length in minutes, as a category total's contribution."""
    return window_minutes(row.start_ts, row.end_ts)


def at_path(payload: Any, path: str) -> Any:
    """The value at a dotted path such as ``fullSleepStats.breathsPerMinute``."""
    current = payload
    for key in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def window_minutes(start: dt.datetime | None, end: dt.datetime | None) -> float:
    """The length of a window in minutes; zero when either end is unknown."""
    if start is None or end is None:
        return 0.0
    return (end - start).total_seconds() / 60


def duration_minutes(value: Any) -> float | None:
    """A Google ``Duration`` such as ``"3600s"``, in minutes."""
    duration = parse_offset(value)
    return None if duration is None else duration.total_seconds() / 60


def local_window(
    segment: dict[str, Any],
) -> tuple[dt.datetime | None, dt.datetime | None]:
    """A nested window's start and end as the user's clock showed them."""
    start = civil_from(
        parse_timestamp(segment.get("startTime")),
        parse_offset(segment.get("startUtcOffset")),
    )
    end = civil_from(
        parse_timestamp(segment.get("endTime")),
        parse_offset(segment.get("endUtcOffset")),
    )
    return start, end
