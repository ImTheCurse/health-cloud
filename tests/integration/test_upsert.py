"""The idempotent write, against real Postgres.

``ON CONFLICT`` is a property of the database, not of our code: a fake cannot
tell us whether the conflict target matches, whether the second write updates
instead of raising, or whether the surrogate key stays put. So these run against
the real thing and skip when it is absent.
"""

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from server.db.upsert import replace_segments, upsert_data_point, upsert_many
from server.models.const import SegmentType
from server.models.datapoint import (
    ObservationTimeInterval,
    SessionSegment,
    SessionTimeInterval,
)

USER = "1234567890123456789"
NOW = dt.datetime(2026, 9, 28, 12, 0, tzinfo=dt.UTC)


def a_point(record_id="rec-1", steps=100, data_type="steps", **overrides):
    defaults = dict(
        health_user_id=USER,
        data_type=data_type,
        record_id=record_id,
        start_ts=dt.datetime(2026, 9, 27, 9, 0, tzinfo=dt.UTC),
        end_ts=dt.datetime(2026, 9, 27, 10, 0, tzinfo=dt.UTC),
        local_start=dt.datetime(2026, 9, 27, 11, 0),
        local_end=dt.datetime(2026, 9, 27, 12, 0),
        civil_date=dt.date(2026, 9, 27),
        value_numeric=Decimal(steps),
        value_unit="count",
        value={"count": str(steps)},
        raw={"name": f"users/me/dataTypes/steps/dataPoints/{record_id}"},
        fetched_at=NOW,
    )
    return ObservationTimeInterval(**{**defaults, **overrides})


def rows(session, table=ObservationTimeInterval):
    return list(session.exec(select(table)))


def test_a_new_record_is_inserted(session):
    row_id = upsert_data_point(session, a_point())
    session.commit()

    written = rows(session)
    assert len(written) == 1
    assert written[0].id == row_id
    assert written[0].value_numeric == Decimal(100)


def test_the_same_record_twice_leaves_one_row(session):
    """The 7-day redelivery window makes this the normal case, not an edge."""
    upsert_data_point(session, a_point())
    upsert_data_point(session, a_point())
    session.commit()

    assert len(rows(session)) == 1


def test_a_correction_overwrites_the_value(session):
    upsert_data_point(session, a_point(steps=100))
    upsert_data_point(session, a_point(steps=250))
    session.commit()

    written = rows(session)
    assert len(written) == 1
    assert written[0].value_numeric == Decimal(250)
    assert written[0].value == {"count": "250"}


def test_the_surrogate_id_does_not_move_on_update(session):
    """``session_segments`` point at it, so a changing id would orphan them."""
    first = upsert_data_point(session, a_point())
    second = upsert_data_point(session, a_point(steps=999))
    session.commit()

    assert first == second


def test_the_natural_key_includes_the_data_type(session):
    """Two types can share a record id without colliding."""
    upsert_data_point(session, a_point(data_type="steps"))
    upsert_data_point(session, a_point(data_type="distance"))
    session.commit()

    assert len(rows(session)) == 2


def test_the_natural_key_includes_the_user(session):
    upsert_data_point(session, a_point())
    upsert_data_point(session, a_point(health_user_id="9999999999999999999"))
    session.commit()

    assert len(rows(session)) == 2


def test_the_raw_payload_is_required(session):
    """A row that lost its source payload cannot be re-derived from anything."""
    with pytest.raises(IntegrityError):
        upsert_data_point(session, a_point(raw=None))
        session.commit()


def test_local_time_keeps_no_timezone(session):
    """Attaching UTC to the user's wall clock is the bug this column prevents."""
    upsert_data_point(session, a_point())
    session.commit()

    written = rows(session)[0]
    assert written.local_start == dt.datetime(2026, 9, 27, 11, 0)
    assert written.local_start.tzinfo is None
    assert written.start_ts.tzinfo is not None


def test_a_tombstone_is_written_not_a_delete(session):
    upsert_data_point(session, a_point())
    upsert_data_point(session, a_point(deleted_at=NOW))
    session.commit()

    written = rows(session)
    assert len(written) == 1
    assert written[0].deleted_at is not None


# --- sessions and their segments ---


def a_session(record_id="sleep-1"):
    return SessionTimeInterval(
        health_user_id=USER,
        data_type="sleep",
        record_id=record_id,
        start_ts=dt.datetime(2026, 9, 26, 22, 0, tzinfo=dt.UTC),
        end_ts=dt.datetime(2026, 9, 27, 6, 0, tzinfo=dt.UTC),
        civil_date=dt.date(2026, 9, 26),
        value={"type": "STAGES", "minutesToFallAsleep": 12},
        raw={"sleep": {"type": "STAGES"}},
        fetched_at=NOW,
    )


def a_stage(label, start_hour):
    start = dt.datetime(2026, 9, 26, 22, 0, tzinfo=dt.UTC) + dt.timedelta(
        hours=start_hour
    )
    return SessionSegment(
        session_id=0,  # replace_segments sets it
        segment_type=SegmentType.SLEEP_STAGE,
        label=label,
        start_ts=start,
        end_ts=start + dt.timedelta(hours=1),
        value={"type": label},
    )


def test_segments_are_attached_to_their_session(session):
    session_id = upsert_data_point(session, a_session())
    replace_segments(session, session_id, [a_stage("LIGHT", 0), a_stage("DEEP", 1)])
    session.commit()

    segments = list(session.exec(select(SessionSegment)))
    assert len(segments) == 2
    assert {s.label for s in segments} == {"LIGHT", "DEEP"}
    assert all(s.session_id == session_id for s in segments)


def test_a_corrected_session_replaces_its_stages(session):
    """Stages have no id of Google's own, so a redelivery must not accumulate."""
    session_id = upsert_data_point(session, a_session())
    replace_segments(session, session_id, [a_stage("LIGHT", 0), a_stage("DEEP", 1)])
    session.commit()

    again = upsert_data_point(session, a_session())
    replace_segments(session, again, [a_stage("REM", 3)])
    session.commit()

    segments = list(session.exec(select(SessionSegment)))
    assert len(segments) == 1
    assert segments[0].label == "REM"


def test_the_segment_type_records_googles_own_name(session):
    """Google names these per data type; the column is where that vocabulary
    lives, since the table name cannot hold four of them."""
    session_id = upsert_data_point(session, a_session())
    replace_segments(session, session_id, [a_stage("LIGHT", 0)])
    session.commit()

    assert list(session.exec(select(SessionSegment)))[0].segment_type == "SLEEP_STAGE"


# --- the batched path ---


def test_a_batch_is_written(session):
    points = [a_point(record_id=f"b{n}", steps=n) for n in range(10)]

    assert upsert_many(session, points) == 10
    session.commit()

    assert len(rows(session)) == 10


def test_a_batch_is_idempotent(session):
    points = [a_point(record_id=f"b{n}") for n in range(5)]

    upsert_many(session, points)
    upsert_many(session, points)
    session.commit()

    assert len(rows(session)) == 5


def test_a_batch_updates_what_is_already_there(session):
    upsert_data_point(session, a_point(record_id="b1", steps=100))
    session.commit()

    upsert_many(session, [a_point(record_id="b1", steps=750)])
    session.commit()

    written = rows(session)
    assert len(written) == 1
    assert written[0].value_numeric == Decimal(750)


def test_two_versions_of_one_record_in_one_batch_do_not_break_it(session):
    """Postgres refuses an ON CONFLICT statement that would touch the same row
    twice -- "cannot affect row a second time" -- and a single page can legitimately
    carry a record and a correction to it. The later one wins, which is what a
    row-at-a-time loop would have left behind."""
    batch = [a_point(record_id="same", steps=1), a_point(record_id="same", steps=2)]

    upsert_many(session, batch)
    session.commit()

    written = rows(session)
    assert len(written) == 1
    assert written[0].value_numeric == Decimal(2)


def test_a_batch_spanning_tables_writes_each_one(session):
    """A mixed batch cannot go in one statement, so it is grouped per table."""
    from server.models.datapoint import ObservationSampleTime

    sample = ObservationSampleTime(
        health_user_id=USER,
        data_type="weight",
        record_id="w1",
        start_ts=NOW,
        end_ts=NOW,
        civil_date=dt.date(2026, 9, 28),
        value={"mass": {"value": 81.4, "unit": "kg"}},
        raw={"weight": {}},
        fetched_at=NOW,
    )

    assert upsert_many(session, [a_point(record_id="i1"), sample]) == 2
    session.commit()

    assert len(rows(session)) == 1
    assert len(rows(session, ObservationSampleTime)) == 1


def test_an_empty_batch_does_nothing(session):
    assert upsert_many(session, []) == 0
