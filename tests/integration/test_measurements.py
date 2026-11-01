"""The read repository, against real Postgres.

Values come back decrypted, and the filters that remain in SQL -- user, type,
civil date, tombstone -- are the ones on plaintext columns.
"""

import datetime as dt
from decimal import Decimal

from server.db.measurements import MeasurementRepository
from server.db.upsert import replace_segments, upsert_data_point, upsert_many
from server.models.const import SegmentType
from server.models.datapoint import (
    ObservationSampleTime,
    SessionSegment,
    SessionTimeInterval,
)

USER = "1234567890123456789"
NOW = dt.datetime(2026, 9, 28, 12, 0, tzinfo=dt.UTC)


def heart_rate(record_id, day, bpm, *, user=USER, data_type="heart-rate", **extra):
    moment = dt.datetime.combine(day, dt.time(9), tzinfo=dt.UTC)
    return ObservationSampleTime(
        health_user_id=user,
        data_type=data_type,
        record_id=record_id,
        start_ts=moment,
        civil_date=day,
        value_numeric=Decimal(bpm),
        value_unit="bpm",
        value={"beatsPerMinute": bpm},
        raw={"heartRate": {"beatsPerMinute": bpm}},
        fetched_at=NOW,
        **extra,
    )


def read(session, start=dt.date(2026, 9, 1), end=dt.date(2026, 10, 1), **kwargs):
    return MeasurementRepository(session).measurements(
        ObservationSampleTime,
        health_user_id=USER,
        data_type="heart-rate",
        start=start,
        end=end,
        **kwargs,
    )


def test_values_come_back_decrypted_in_date_order(session):
    upsert_many(
        session,
        [
            heart_rate("b", dt.date(2026, 9, 21), 64),
            heart_rate("a", dt.date(2026, 9, 20), 72),
        ],
    )

    found = read(session)

    assert [m.value_numeric for m in found] == [Decimal(72), Decimal(64)]
    assert {m.value_unit for m in found} == {"bpm"}


def test_the_range_is_half_open_on_civil_date(session):
    upsert_many(
        session,
        [
            heart_rate("before", dt.date(2026, 9, 19), 60),
            heart_rate("first", dt.date(2026, 9, 20), 61),
            heart_rate("end", dt.date(2026, 9, 22), 62),
        ],
    )

    found = read(session, start=dt.date(2026, 9, 20), end=dt.date(2026, 9, 22))

    assert [m.value_numeric for m in found] == [Decimal(61)]


def test_other_users_types_and_tombstones_are_left_out(session):
    day = dt.date(2026, 9, 20)
    upsert_many(
        session,
        [
            heart_rate("mine", day, 70),
            heart_rate("theirs", day, 80, user="someone-else"),
            heart_rate("weight", day, 90, data_type="weight"),
            heart_rate("deleted", day, 99, deleted_at=NOW),
        ],
    )

    assert [m.value_numeric for m in read(session)] == [Decimal(70)]


def test_the_payload_is_decrypted_only_when_asked_for(session):
    upsert_many(session, [heart_rate("a", dt.date(2026, 9, 20), 72)])

    assert read(session)[0].value is None
    assert read(session, with_value=True)[0].value == {"beatsPerMinute": 72}


def test_segments_come_back_per_session_with_their_labels(session):
    sleep_id = upsert_data_point(
        session,
        SessionTimeInterval(
            health_user_id=USER,
            data_type="sleep",
            record_id="night",
            civil_date=dt.date(2026, 9, 20),
            raw={"sleep": {}},
            fetched_at=NOW,
        ),
    )
    start = dt.datetime(2026, 9, 20, 23, 0, tzinfo=dt.UTC)
    replace_segments(
        session,
        sleep_id,
        [
            SessionSegment(
                session_id=0,
                segment_type=SegmentType.SLEEP_STAGE,
                label=label,
                start_ts=start + dt.timedelta(hours=offset),
            )
            for offset, label in [(1, "REM"), (0, "DEEP")]
        ],
    )

    found = MeasurementRepository(session).segments([sleep_id])

    assert [s.label for s in found[sleep_id]] == ["DEEP", "REM"]


def test_no_session_ids_reads_nothing(session):
    assert MeasurementRepository(session).segments([]) == {}
