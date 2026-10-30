"""Idempotent writes for the measurement tables.
Delivery is at-least-once with 7 days of retries, so the same record arrives
more than once as a matter of course. Dedupe lives here, at the data level:
always fetch, always write, and let the second write be a no-op.
"""

from typing import Any

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import class_mapper
from sqlmodel import Session

from server.models.datapoint import DataPointBase, SessionSegment

#: The natural key, and so the conflict target. One row per record, per data
#: type, per user -- see ``_table_args`` in the models.
CONFLICT_COLUMNS = ("health_user_id", "data_type", "record_id")

#: Never overwritten by a repeat write. The surrogate key must not move, because
#: ``session_segments`` rows point at it, and the natural key is what matched in
#: the first place.
_PRESERVED = frozenset({"id", *CONFLICT_COLUMNS})


def upsert_data_point(session: Session, point: DataPointBase) -> int:
    """Insert ``point``, or update the row already holding its record id.

    Returns:
        The surrogate id of the inserted or updated row, so a session's segments
        have a parent to point at.

    One statement, so there is no window between a read and a write for a
    concurrent writer to occupy.
    """
    table = type(point)
    values = _column_values(point)

    insertion = insert(table).values(**values)
    updates = {
        name: insertion.excluded[name] for name in values if name not in _PRESERVED
    }
    statement = insertion.on_conflict_do_update(
        index_elements=list(CONFLICT_COLUMNS), set_=updates
    ).returning(class_mapper(table).columns["id"])

    return int(session.execute(statement).scalar_one())


def upsert_many(session: Session, points: list[DataPointBase]) -> int:
    """Upsert a batch of rows in one statement per table.

    Returns:
        How many rows were sent.

    Why this exists, rather than looping ``upsert_data_point``: a day of heart-rate
    is roughly 34,000 points, and one statement each is 34,000 round trips. That is
    slow enough to matter for correctness, not just for patience -- a fetch that
    outruns the consumer's ``ack_wait`` gets its message redelivered underneath it,
    so the same work runs twice concurrently.

    No ids come back, so this is only for rows that nothing needs to point at. A
    session has segments to attach and goes through ``upsert_data_point`` one at a
    time.

    Rows are de-duplicated by natural key before sending: Postgres refuses an
    ``ON CONFLICT`` statement that would touch the same row twice ("cannot affect
    row a second time"), and a single page can legitimately carry two versions of
    one record.
    """
    if not points:
        return 0

    by_table: dict[type[DataPointBase], dict[tuple[Any, ...], dict[str, Any]]] = {}
    for point in points:
        values = _column_values(point)
        key = tuple(values[column] for column in CONFLICT_COLUMNS)
        # Last one wins, matching what a row-at-a-time loop would leave behind.
        by_table.setdefault(type(point), {})[key] = values

    sent = 0
    for table, rows in by_table.items():
        batch = list(rows.values())
        insertion = insert(table).values(batch)
        updates = {
            name: insertion.excluded[name]
            for name in batch[0]
            if name not in _PRESERVED
        }
        session.execute(
            insertion.on_conflict_do_update(
                index_elements=list(CONFLICT_COLUMNS), set_=updates
            )
        )
        sent += len(batch)
    return sent


def replace_segments(
    session: Session, session_id: int, segments: list[SessionSegment]
) -> None:
    """Make ``session_segments`` for one session exactly ``segments``.

    Replace rather than upsert: a segment carries no id of Google's own, so there
    is nothing stable to match a repeat delivery on. The session's record id is
    the identity and its segments are a property of it, so when a corrected sleep
    session arrives with its stages redrawn, the previous stages are wrong and
    must go rather than accumulate alongside.

    Both statements run in the caller's transaction, so a reader never observes a
    session that has momentarily lost its stages.
    """
    columns = class_mapper(SessionSegment).columns
    session.execute(delete(SessionSegment).where(columns["session_id"] == session_id))
    for segment in segments:
        segment.session_id = session_id
        session.add(segment)


def _column_values(point: DataPointBase) -> dict[str, Any]:
    """The instance's column values, excluding an unset surrogate key.

    ``model_dump()`` is not used: it would include ``id=None``, sending an
    explicit null for the serial column and overriding the sequence default.
    """
    return {
        column.name: getattr(point, column.name)
        for column in class_mapper(type(point)).columns
        if not (column.name == "id" and getattr(point, "id", None) is None)
    }
