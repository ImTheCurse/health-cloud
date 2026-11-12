"""What an attacker holding the database actually sees.

Rows are written through the normal path, then read back with plain SQL that
bypasses the models and their column types -- exactly what a SQL injection or a
dump gets. Nothing a measurement says may appear in it.

The column inventory below is exhaustive on purpose: a column added to a
measurement table without deciding whether it is a value or structure fails
here, rather than quietly landing in plaintext.

Where the test arguments come from:

- ``session`` is the fixture in ``tests/integration/conftest.py``: a session on
  a throwaway database, ``health_cloud_integration_<pid>``, created when the test
  run starts and dropped when it ends. Each test runs inside a transaction that
  is rolled back afterwards, so nothing written here outlives the test, and the
  app's own database is never connected to.
- ``written`` is the fixture below: that session, with one row of known
  content in every table that holds health data.
- ``columns`` comes from ``@pytest.mark.parametrize`` over ``INVENTORY``: each
  test taking it runs once per table, and its id in the report is the table name.
"""

import datetime as dt
import json
from dataclasses import dataclass
from decimal import Decimal

import pytest
from sqlalchemy import text

from server.crypto.const import COMPRESSED_FLAG, DATA_KEY_VERSION
from server.db.upsert import replace_segments, upsert_data_point, upsert_many
from server.models.const import SegmentType
from server.models.datapoint import (
    ObservationSampleTime,
    ObservationTimeInterval,
    SessionSegment,
    SessionTimeInterval,
    UnknownDataPoint,
)
from server.models.notification import RawNotification
from tests.google_webhook import BATCHED_NOTIFICATION

USER = "1234567890123456789"
NOW = dt.datetime(2026, 9, 28, 12, 0, tzinfo=dt.UTC)
DAY = dt.date(2026, 9, 27)

#: Strings that only a decrypted value contains. Each is written somewhere below.
SECRETS = ("beatsPerMinute", "7243", "DEEP", "minutesToFallAsleep", "restingBpm")

#: Every notification fixture in ``tests.google_webhook`` carries two pointers.
BATCHED_POINTERS = 2

MEASUREMENT_TABLES = (
    "observation_time_intervals",
    "observation_sample_times",
    "session_time_intervals",
    "unknown_data_points",
)

#: Encrypted column -> whether it is compressed first.
MEASUREMENT_ENCRYPTED = {
    "value_numeric": False,
    "value_unit": False,
    "value": True,
    "raw": True,
}
MEASUREMENT_PLAINTEXT = {
    "id",
    "health_user_id",
    "data_type",
    "record_id",
    "source_platform",
    "start_ts",
    "end_ts",
    "local_start",
    "local_end",
    "civil_date",
    "deleted_at",
    "fetched_at",
}
SEGMENT_ENCRYPTED = {"label": False, "value": True}
SEGMENT_PLAINTEXT = {
    "id",
    "session_id",
    "segment_type",
    "start_ts",
    "end_ts",
    "local_start",
    "local_end",
}
NOTIFICATION_ENCRYPTED = {"body": True}
NOTIFICATION_PLAINTEXT = {"id", "received_at", "request_id", "pointer_count"}


@dataclass(frozen=True)
class TableColumns:
    """One table's columns, each classified as an encrypted value or structure."""

    table: str
    #: Encrypted column -> whether it is compressed before encryption.
    encrypted: dict[str, bool]
    plaintext: set[str]


INVENTORY = [
    *[
        TableColumns(table, MEASUREMENT_ENCRYPTED, MEASUREMENT_PLAINTEXT)
        for table in MEASUREMENT_TABLES
    ],
    TableColumns("session_segments", SEGMENT_ENCRYPTED, SEGMENT_PLAINTEXT),
    TableColumns("raw_notifications", NOTIFICATION_ENCRYPTED, NOTIFICATION_PLAINTEXT),
]

per_table = pytest.mark.parametrize(
    "columns", INVENTORY, ids=[columns.table for columns in INVENTORY]
)


def common(**overrides):
    return (
        dict(
            health_user_id=USER,
            start_ts=dt.datetime(2026, 9, 27, 9, 0, tzinfo=dt.UTC),
            end_ts=dt.datetime(2026, 9, 27, 10, 0, tzinfo=dt.UTC),
            civil_date=DAY,
            fetched_at=NOW,
        )
        | overrides
    )


@pytest.fixture
def written(session):
    """One row in every table that holds health data."""
    upsert_many(
        session,
        [
            ObservationTimeInterval(
                **common(data_type="steps", record_id="s1"),
                value_numeric=Decimal(7243),
                value_unit="count",
                value={"count": "7243"},
                raw={"steps": {"count": "7243"}},
            ),
            ObservationSampleTime(
                **common(data_type="heart-rate", record_id="h1"),
                value_numeric=Decimal(72),
                value_unit="bpm",
                value={"beatsPerMinute": 72},
                raw={"heartRate": {"beatsPerMinute": 72}},
            ),
            UnknownDataPoint(
                **common(data_type="daily-resting-heart-rate", record_id="r1"),
                value={"restingBpm": 55},
                raw={"dailyRestingHeartRate": {"restingBpm": 55}},
            ),
        ],
    )
    sleep_id = upsert_data_point(
        session,
        SessionTimeInterval(
            **common(data_type="sleep", record_id="sl1"),
            value={"type": "STAGES", "minutesToFallAsleep": 12},
            raw={"sleep": {"minutesToFallAsleep": 12, "stages": ["DEEP"] * 50}},
        ),
    )
    replace_segments(
        session,
        sleep_id,
        [
            SessionSegment(
                session_id=sleep_id,
                segment_type=SegmentType.SLEEP_STAGE,
                label="DEEP",
                start_ts=dt.datetime(2026, 9, 27, 1, 0, tzinfo=dt.UTC),
                value={"type": "DEEP"},
            )
        ],
    )
    session.add(
        RawNotification(
            received_at=NOW,
            request_id="req-1",
            body=json.loads(BATCHED_NOTIFICATION) + [{"beatsPerMinute": 72}],
            pointer_count=BATCHED_POINTERS,
        )
    )
    session.commit()
    return session


def raw_rows(session, table):
    """Every row as Postgres stores it, with no model or column type involved."""
    result = session.connection().execute(text(f"SELECT * FROM {table}"))
    return [dict(row._mapping) for row in result]


def column_types(session, table):
    result = session.connection().execute(
        text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = :table"
        ),
        {"table": table},
    )
    return dict(result.all())


def as_bytes(value) -> bytes:
    return (
        bytes(value) if isinstance(value, (bytes, memoryview)) else str(value).encode()
    )


@per_table
def test_every_column_is_either_encrypted_or_known_structure(written, columns):
    types = column_types(written, columns.table)

    assert set(types) == set(columns.encrypted) | columns.plaintext
    for column in columns.encrypted:
        assert types[column] == "bytea", column


@per_table
def test_no_measurement_is_readable_in_the_database(written, columns):
    rows = raw_rows(written, columns.table)
    assert rows, f"nothing was written to {columns.table}"

    for row in rows:
        stored = b" ".join(as_bytes(value) for value in row.values())
        for secret in SECRETS:
            assert secret.encode() not in stored, secret


@per_table
def test_each_encrypted_column_carries_its_header(written, columns):
    """The key version, and the compression flag on JSON columns only."""
    for row in raw_rows(written, columns.table):
        for column, compressed in columns.encrypted.items():
            if row[column] is None:
                continue
            header = as_bytes(row[column])[0]
            expected = DATA_KEY_VERSION | (COMPRESSED_FLAG if compressed else 0)
            assert header == expected, column


def test_values_come_back_decrypted_through_the_models(written):
    from sqlmodel import select

    heart = written.exec(select(ObservationSampleTime)).one()
    assert heart.value_numeric == Decimal(72)
    assert heart.value_unit == "bpm"
    assert heart.value == {"beatsPerMinute": 72}

    segment = written.exec(select(SessionSegment)).one()
    assert segment.label == "DEEP"

    notification = written.exec(select(RawNotification)).one()
    assert notification.body[-1] == {"beatsPerMinute": 72}


def test_an_absent_value_stays_null_rather_than_encrypted(written):
    """A null must stay distinguishable from a value, and ``NOT NULL`` must bite."""
    unknown = raw_rows(written, "unknown_data_points")[0]
    assert unknown["value_numeric"] is None
    assert unknown["value_unit"] is None


def test_the_payload_column_still_refuses_a_missing_payload(session):
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        upsert_data_point(
            session,
            ObservationTimeInterval(
                **common(data_type="steps", record_id="x"), raw=None
            ),
        )
