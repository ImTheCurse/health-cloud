"""A read repository that serves rows from memory."""

import datetime as dt
from decimal import Decimal
from typing import Any

from server.aggregation.series import MeasurementReader
from server.db.measurements import Measurement

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


def reader_over(
    tables: dict[str, type] | None = None, **rows: list[Measurement]
) -> MeasurementReader:
    by_type = {name.replace("_", "-"): found for name, found in rows.items()}
    repository = FakeRepository(by_type, tables)
    return MeasurementReader(repository, USER)  # type: ignore[arg-type]


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
