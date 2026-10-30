"""Helpers for reading Google's payloads.

Parsing only: nothing here talks to the network or the database, so the shapes
can be exercised against captured payloads without either.
"""

import datetime as dt
from decimal import Decimal, InvalidOperation
from typing import Any

#: Google's duration strings are seconds with a trailing "s": "3.5s", "-14400s".
_DURATION_SUFFIX = "s"

#: Keys that are never the measurement: they carry when it happened or where it
#: came from.
_NOT_A_MEASUREMENT = frozenset({"interval", "sampleTime", "dataSource"})


def parse_timestamp(value: Any) -> dt.datetime | None:
    """An RFC-3339 timestamp, as an aware UTC datetime.

    Returns None rather than raising: a payload missing a time is a real case --
    a full-day activity omits the physical interval entirely -- and the column is
    nullable for exactly that reason.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


def parse_offset(value: Any) -> dt.timedelta | None:
    """A ``Duration`` offset such as ``"-14400s"``, as a timedelta.

    This is what makes the local columns derivable: Google sends the absolute
    time plus the offset the user's clock was at, rather than a local timestamp.
    """
    if isinstance(value, int | float):
        return dt.timedelta(seconds=float(value))
    if not isinstance(value, str) or not value:
        return None
    try:
        return dt.timedelta(seconds=float(value.removesuffix(_DURATION_SUFFIX)))
    except ValueError:
        return None


def civil_from(
    moment: dt.datetime | None, offset: dt.timedelta | None
) -> dt.datetime | None:
    """The wall-clock time a user would have seen, with no timezone attached.

    Naive on purpose. The whole point of the civil representation is that it is
    not anchored to a zone: "my Tuesday" is Tuesday where the user was standing,
    and attaching UTC to it would undo that.
    """
    if moment is None:
        return None
    shifted = moment + (offset or dt.timedelta())
    return shifted.replace(tzinfo=None)


def parse_civil(value: Any) -> dt.datetime | None:
    """Google's ``CivilDateTime``, in any of the three shapes it really arrives in.

    Preferred over deriving from an offset when present, since it is what Google
    itself computed.

    Live traffic, 2026-09-28: the real shape nests the parts under ``date`` and
    ``time`` -- ``{"date": {"year", "month", "day"}, "time": {"hours",
    "minutes"}}`` -- which is not what the reference's field list suggested. A
    flat object and an ISO string are both still accepted, because the docs
    describe them and this costs nothing.

    Getting this wrong was survivable but silent: the flat-only version returned
    None for every real payload and the local columns quietly fell back to being
    derived from ``startUtcOffset``. Same answer, by luck, and no error either way.
    """
    if isinstance(value, str):
        parsed = dt.datetime.fromisoformat(value) if _iso_like(value) else None
        return parsed.replace(tzinfo=None) if parsed else None
    if not isinstance(value, dict):
        return None

    nested_date = value.get("date")
    nested_time = value.get("time")
    date_part: dict[str, Any] = nested_date if isinstance(nested_date, dict) else value
    time_part: dict[str, Any] = nested_time if isinstance(nested_time, dict) else value
    try:
        return dt.datetime(
            year=int(date_part["year"]),
            month=int(date_part["month"]),
            day=int(date_part["day"]),
            hour=int(time_part.get("hours", 0)),
            minute=int(time_part.get("minutes", 0)),
            second=int(time_part.get("seconds", 0)),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _iso_like(value: str) -> bool:
    try:
        dt.datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


def scalar_value(payload: Any) -> tuple[Decimal | None, str | None]:
    """The single number in a payload, and its unit -- if there is exactly one.

    Google spells a measurement several ways: a bare number, an int64 inside a
    string, or a quantity object pairing a value with a unit. All three collapse
    to the same pair here so a chart can read one indexed column.

    "Exactly one" is the whole rule, and it is stricter than it looks necessary.
    A sleep session carries ``minutesToFallAsleep`` and ``minutesAfterWakeup``:
    both are numbers, neither is *the* measurement, and picking the first would
    put "12" in the column as though it were the value of a night's sleep. So a
    payload with two candidates is composite, exactly like one with none, and its
    numbers stay in ``value`` where their names still mean something.
    """
    if not isinstance(payload, dict):
        number = _as_decimal(payload)
        return (number, None) if number is not None else (None, None)

    found: list[tuple[Decimal, str | None]] = []
    for key, value in payload.items():
        if key in _NOT_A_MEASUREMENT:
            continue
        if isinstance(value, list):
            # A sub-interval array is structure, not a measurement.
            continue
        if isinstance(value, dict):
            number = _as_decimal(value.get("value"))
            if number is not None:
                unit = value.get("unit")
                found.append((number, unit if isinstance(unit, str) else None))
            continue
        number = _as_decimal(value)
        if number is not None:
            found.append((number, _unit_from_key(key)))

    return found[0] if len(found) == 1 else (None, None)


def _as_decimal(value: Any) -> Decimal | None:
    """A number, however Google spelled it. Bools are not numbers here."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float | Decimal):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation:
            return None
    return None


def _unit_from_key(key: str) -> str | None:
    """The unit implied by a field name, where Google states none separately.

    ``beatsPerMinute`` is a unit as much as ``"kg"`` is; keeping it means a chart
    can label an axis without a lookup table per data type.
    """
    return None if key == "value" else key
