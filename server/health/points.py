"""Turning a Google ``DataPoint`` into rows.

Two steps, kept apart: decide which shape a payload is, then build the row for
that shape. Neither touches the network or the database, so both can be
exercised against captured payloads.

A dataPoint wraps its measurement in a union field named after the data type --
``{"name": ..., "dataSource": ..., "steps": {"interval": {...}, "count": "4210"}}``
-- so the payload of interest is found by elimination rather than by name, which
is what lets a data type we have never heard of still be read.
"""

import datetime as dt
import hashlib
import json
from datetime import date
from typing import Any

from server.health.const import (
    END_TIME_KEY,
    INTERVAL_KEY,
    PHYSICAL_TIME_KEY,
    SAMPLE_TIME_KEY,
    SEED_STRUCTURES,
    SEGMENT_KEYS,
    START_TIME_KEY,
)
from server.health.util import (
    civil_from,
    parse_civil,
    parse_offset,
    parse_timestamp,
    scalar_value,
)
from server.models.const import SegmentType, TimeStructure
from server.models.datapoint import (
    DataPointBase,
    ObservationSampleTime,
    ObservationTimeInterval,
    SessionSegment,
    SessionTimeInterval,
    UnknownDataPoint,
)

#: Envelope keys that are never the measurement.
_ENVELOPE = frozenset({"name", "dataSource", "dataType", "etag"})

#: Which table each structure writes to.
TABLES: dict[TimeStructure, type[DataPointBase]] = {
    TimeStructure.INTERVAL: ObservationTimeInterval,
    TimeStructure.SAMPLE: ObservationSampleTime,
    TimeStructure.SESSION: SessionTimeInterval,
    TimeStructure.UNKNOWN: UnknownDataPoint,
}

#: Which segment type each nested array in a session produces. Google names these
#: per data type and has no umbrella term, so the mapping is explicit.
SEGMENT_TYPES: dict[str, SegmentType] = {
    "stages": SegmentType.SLEEP_STAGE,
    "shortAwakenings": SegmentType.SLEEP_STAGE,
    "outOfBedSegments": SegmentType.OUT_OF_BED_SEGMENT,
    "splits": SegmentType.SPLIT_SUMMARY,
    "events": SegmentType.EXERCISE_EVENT,
}


def measurement_of(point: dict[str, Any]) -> tuple[str | None, Any]:
    """The union field's name and contents.

    By elimination, so an unrecognised data type is still readable: whatever is
    left after the envelope keys is the measurement.
    """
    for key, value in point.items():
        if key not in _ENVELOPE:
            return key, value
    return None, None


def classify(data_type: str, payload: Any) -> TimeStructure:
    """Which of Google's three time shapes this payload carries.

    The payload decides, with one exception it cannot: ``SessionTimeInterval``
    and ``ObservationTimeInterval`` have *identical* fields, so a session is told
    from an interval either by carrying sub-intervals or by the seed table. A
    session whose segments happen to be empty and whose type is unseeded is read
    as an interval -- the row still lands with its time and payload intact, and
    only the choice of table is wrong.
    """
    if not isinstance(payload, dict):
        return TimeStructure.UNKNOWN

    if SAMPLE_TIME_KEY in payload:
        return TimeStructure.SAMPLE

    if INTERVAL_KEY in payload:
        if any(payload.get(key) for key in SEGMENT_KEYS):
            return TimeStructure.SESSION
        seeded = SEED_STRUCTURES.get(data_type)
        return seeded if seeded is not None else TimeStructure.INTERVAL

    return TimeStructure.UNKNOWN


def build(
    point: dict[str, Any],
    *,
    health_user_id: str,
    data_type: str,
    fetched_at: dt.datetime,
    deleted_at: dt.datetime | None = None,
) -> tuple[DataPointBase, list[SessionSegment]]:
    """One row for ``point``, plus its segments if it is a session.

    The whole dataPoint goes into ``raw`` regardless of how well the rest of it
    was understood, which is what makes a modelling mistake correctable from our
    own database instead of from Google's 7-day window.
    """
    _, payload = measurement_of(point)
    structure = classify(data_type, payload)
    times = _times(payload, structure)
    numeric, unit = scalar_value(payload)

    row = TABLES[structure](
        health_user_id=health_user_id,
        data_type=data_type,
        record_id=record_id_of(point),
        value=payload,
        raw=point,
        value_numeric=numeric,
        value_unit=unit,
        fetched_at=fetched_at,
        deleted_at=deleted_at,
        **times,
    )
    segments = _segments(payload) if structure is TimeStructure.SESSION else []
    return row, segments


def record_id_of(point: dict[str, Any]) -> str:
    """A stable identity for this measurement.

    Google's reference describes a ``name`` of the form
    ``users/{user}/dataTypes/{type}/dataPoints/{id}``, and where it is present its
    trailing segment is used. **Live traffic does not include it**: a real
    ``steps`` point carries exactly ``{"dataSource", "steps"}``
    -- no ``name``, no ``recordId``, nothing Google calls an identifier.

    So the identity is *derived*, as a digest of the fields that say which
    measurement this is: the payload's time window and its source. That keeps the
    one property the natural key exists for -- re-fetching the same measurement
    produces the same key, so the upsert updates instead of duplicating.

    What it deliberately excludes is the measured value. Keying on the value would
    make a *correction* look like a different record and insert a second row
    alongside the one it was meant to replace, which is precisely the silent
    duplication the tombstone and upsert design exists to avoid.
    """
    name = point.get("name")
    if isinstance(name, str) and name:
        return name.rsplit("/", 1)[-1] or name
    return _derived_id(point)


def _derived_id(point: dict[str, Any]) -> str:
    """A digest of what identifies a measurement, when Google names none.

    Uses the time window (or bare date for a daily summary) and data source.
    Both are stable across a re-fetch and a correction to the value, which makes
    this usable as the upsert's conflict target.
    """
    _, payload = measurement_of(point)
    parts: list[str] = []

    if isinstance(payload, dict):
        interval = payload.get(INTERVAL_KEY)
        if isinstance(interval, dict):
            parts += [
                str(interval.get(START_TIME_KEY, "")),
                str(interval.get(END_TIME_KEY, "")),
            ]
        sample = payload.get(SAMPLE_TIME_KEY)
        if isinstance(sample, dict):
            parts.append(str(sample.get(PHYSICAL_TIME_KEY, "")))
        civil_date = _bare_date(payload)
        if civil_date is not None:
            parts.append(civil_date.isoformat())

    source = point.get("dataSource")
    if isinstance(source, dict):
        # Sorted, so a re-fetch that happens to order the keys differently still
        # digests to the same id.
        parts.append(json.dumps(source, sort_keys=True))

    if not any(parts):
        raise ValueError(
            "dataPoint carries neither a name nor any time or source to identify it"
        )
    return "d-" + hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]


def _times(payload: Any, structure: TimeStructure) -> dict[str, Any]:
    """The four time columns plus the civil date, for whichever shape this is."""
    if not isinstance(payload, dict):
        return {}

    if structure is TimeStructure.UNKNOWN:
        # A daily summary carries a bare `date` rather than an interval or a
        # sample time -- a fourth shape, such as `daily-resting-heart-rate`. Its
        # payload is safe in the unknown table, but without a date it would not be
        # queryable by time, and reading the one field it does have costs nothing.
        return _columns(None, None, None, None) | {"civil_date": _bare_date(payload)}

    if structure is TimeStructure.SAMPLE:
        sample = payload.get(SAMPLE_TIME_KEY) or {}
        moment = parse_timestamp(sample.get(PHYSICAL_TIME_KEY))
        local = parse_civil(sample.get("civilTime")) or civil_from(
            moment, parse_offset(sample.get("utcOffset"))
        )
        # Both ends hold the instant, so "everything between two times" is one
        # query shape across all three tables rather than three.
        return _columns(moment, moment, local, local)

    interval = payload.get(INTERVAL_KEY) or {}
    start = parse_timestamp(interval.get("startTime"))
    end = parse_timestamp(interval.get("endTime"))
    local_start = parse_civil(interval.get("civilStartTime")) or civil_from(
        start, parse_offset(interval.get("startUtcOffset"))
    )
    local_end = parse_civil(interval.get("civilEndTime")) or civil_from(
        end, parse_offset(interval.get("endUtcOffset"))
    )
    return _columns(start, end, local_start, local_end)


def _columns(
    start: dt.datetime | None,
    end: dt.datetime | None,
    local_start: dt.datetime | None,
    local_end: dt.datetime | None,
) -> dict[str, Any]:
    """Assemble the time columns, deriving the aggregation date.

    ``civil_date`` prefers the local start: the dashboard groups by the day the
    user experienced, and only falls back to the UTC date when Google sent no
    local time at all.
    """
    anchor = local_start or local_end or start
    return {
        "start_ts": start,
        "end_ts": end,
        "local_start": local_start,
        "local_end": local_end,
        "civil_date": anchor.date() if anchor is not None else None,
    }


def _bare_date(payload: dict[str, Any]) -> date | None:
    """The ``date`` of a daily summary, if that is all the time it has."""
    moment = parse_civil(payload.get("date"))
    return moment.date() if moment is not None else None


def _segments(payload: Any) -> list[SessionSegment]:
    """Rows for a session's sub-intervals: sleep stages, laps, pause events."""
    if not isinstance(payload, dict):
        return []

    segments: list[SessionSegment] = []
    for key in SEGMENT_KEYS:
        entries = payload.get(key)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            segments.append(_segment(key, entry))
    return segments


def _segment(key: str, entry: dict[str, Any]) -> SessionSegment:
    """One sub-interval.

    A segment's times sit either directly on it or inside a nested ``interval``,
    depending on the data type, so both are tried.
    """
    nested = entry.get(INTERVAL_KEY)
    interval: dict[str, Any] = nested if isinstance(nested, dict) else entry
    start = parse_timestamp(interval.get("startTime"))
    end = parse_timestamp(interval.get("endTime"))
    label = entry.get("type")
    return SessionSegment(
        session_id=0,  # set when the parent row's id is known
        segment_type=SEGMENT_TYPES[key],
        label=label if isinstance(label, str) else None,
        start_ts=start,
        end_ts=end,
        local_start=civil_from(start, parse_offset(interval.get("startUtcOffset"))),
        local_end=civil_from(end, parse_offset(interval.get("endUtcOffset"))),
        value=entry,
    )
