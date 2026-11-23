"""A read repository that serves rows from memory."""

import datetime as dt
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from server.aggregation.series import MeasurementReader
from server.db.measurements import Measurement
from server.rollup.hours import StoredHour

USER = "fake-health-user"


class FakeRepository:
    """Serves ``rows[data_type]``, honouring the date range like the real one.

    A type named in ``tables`` is served only from that table, as a real row
    lives in exactly one; any other type is served whichever table is asked.
    """

    def __init__(
        self, rows: dict[str, list[Measurement]], tables: dict[str, type] | None = None
    ) -> None:
        self._rows = rows
        self._tables = tables or {}
        self.calls: list[dict[str, Any]] = []

    def measurements(self, table, *, data_type, start, end, **kwargs):
        self.calls.append({"table": table, "data_type": data_type, **kwargs})
        if self._tables.get(data_type, table) is not table:
            return []
        return [
            row
            for row in self._rows.get(data_type, [])
            if row.civil_date is not None and start <= row.civil_date < end
        ]


class FakeHours:
    """Serves stored hourly summaries, honouring the date range like the real one.

    Every hour is served whatever platforms are asked for: the real filter is
    a ``WHERE`` clause, tested against Postgres.
    """

    def __init__(self, hours: list[StoredHour]) -> None:
        self._hours = hours
        self.calls: list[dict[str, Any]] = []

    def read(self, health_user_id, start, end, platforms):
        self.calls.append({"start": start, "end": end, "platforms": platforms})
        return [hour for hour in self._hours if start <= hour.civil_date < end]


def reader_over(
    tables: dict[str, type] | None = None,
    hours: list[StoredHour] | None = None,
    **rows: list[Measurement],
) -> MeasurementReader:
    by_type = {name.replace("_", "-"): found for name, found in rows.items()}
    repository = FakeRepository(by_type, tables)
    return MeasurementReader(repository, USER, FakeHours(hours or []))  # type: ignore[arg-type]


def stored_hour(
    hour_start: dt.datetime,
    samples: Sequence[float] = (),
    zone_minutes: dict[str, float] | None = None,
) -> StoredHour:
    """One hour's summary, as the rollup would have built it from ``samples``."""
    summary: dict[str, Any] = {"zone_minutes": zone_minutes or {}}
    if samples:
        summary |= {
            "count": len(samples),
            "sum": float(sum(samples)),
            "min": min(samples),
            "max": max(samples),
        }
    return StoredHour(hour_start, hour_start.date(), summary)


def row(
    local_start: dt.datetime | None = None,
    *,
    minutes: float = 0,
    value: Any = None,
    numeric: float | str | None = None,
    civil_date: dt.date | None = None,
    local_end: dt.datetime | None = None,
) -> Measurement:
    """A measurement whose local and UTC clocks agree, for readable tests."""
    end = (
        local_end
        if local_end is not None
        else (local_start + dt.timedelta(minutes=minutes) if local_start else None)
    )
    return Measurement(
        id=1,
        civil_date=civil_date or (local_start.date() if local_start else None),
        start_ts=local_start.replace(tzinfo=dt.UTC) if local_start else None,
        end_ts=end.replace(tzinfo=dt.UTC) if end else None,
        local_start=local_start,
        local_end=end,
        value_numeric=None if numeric is None else Decimal(str(numeric)),
        value_unit=None,
        value=value,
    )
