"""Reading measurements back, decrypted.

Values are encrypted at rest, so nothing here can filter, sum or average them in
SQL: the database narrows by user, data type and civil date, which are plaintext
and indexed, and the caller aggregates what comes back. Each read selects only
the columns it returns, because every encrypted column loaded is a decryption --
and ``raw``, the largest, is never loaded at all.
"""

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

# SQLAlchemy's `select`, not SQLModel's: SQLModel's is typed for at most four
# columns, and a read that names its columns to avoid decrypting the rest needs
# more. `Session.execute` rather than `exec`, which is typed for SQLModel's own.
from sqlalchemy import select
from sqlmodel import Session, col

from server.models.datapoint import DataPointBase, SessionSegment


@dataclass(frozen=True)
class Measurement:
    """One stored measurement, decrypted. ``value`` is set only when asked for."""

    id: int
    civil_date: dt.date | None
    start_ts: dt.datetime | None
    end_ts: dt.datetime | None
    local_start: dt.datetime | None
    local_end: dt.datetime | None
    value_numeric: Decimal | None
    value_unit: str | None
    value: Any = None


@dataclass(frozen=True)
class Segment:
    """One sub-interval of a session -- a sleep stage, a lap -- decrypted."""

    session_id: int
    segment_type: str
    label: str | None
    start_ts: dt.datetime | None
    end_ts: dt.datetime | None
    local_start: dt.datetime | None
    local_end: dt.datetime | None


class MeasurementRepository:
    """Read access to the measurement tables, bound to one session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def measurements(
        self,
        table: type[DataPointBase],
        *,
        health_user_id: str,
        data_type: str,
        start: dt.date,
        end: dt.date,
        with_value: bool = False,
    ) -> list[Measurement]:
        """Live measurements of one type whose civil date is in ``[start, end)``.

        Tombstoned rows are left out. Ordered by civil date, then start time.
        ``with_value`` also decrypts the type-specific payload, which a chart of
        a single number does not need.
        """
        columns: list[Any] = [
            col(table.id),
            col(table.civil_date),
            col(table.start_ts),
            col(table.end_ts),
            col(table.local_start),
            col(table.local_end),
            col(table.value_numeric),
            col(table.value_unit),
        ]
        if with_value:
            columns.append(col(table.value))

        statement = (
            select(*columns)
            .where(col(table.health_user_id) == health_user_id)
            .where(col(table.data_type) == data_type)
            .where(col(table.civil_date) >= start)
            .where(col(table.civil_date) < end)
            .where(col(table.deleted_at).is_(None))
            .order_by(col(table.civil_date), col(table.start_ts))
        )
        return [Measurement(*row) for row in self._session.execute(statement)]

    def segments(self, session_ids: Sequence[int]) -> dict[int, list[Segment]]:
        """The segments of each session, keyed by session id, in time order.

        A session with no segments is absent from the result rather than mapped
        to an empty list.
        """
        if not session_ids:
            return {}

        statement = (
            select(
                col(SessionSegment.session_id),
                col(SessionSegment.segment_type),
                col(SessionSegment.label),
                col(SessionSegment.start_ts),
                col(SessionSegment.end_ts),
                col(SessionSegment.local_start),
                col(SessionSegment.local_end),
            )
            .where(col(SessionSegment.session_id).in_(session_ids))
            .order_by(col(SessionSegment.session_id), col(SessionSegment.start_ts))
        )
        found: dict[int, list[Segment]] = {}
        for row in self._session.execute(statement):
            segment = Segment(*row)
            found.setdefault(segment.session_id, []).append(segment)
        return found
