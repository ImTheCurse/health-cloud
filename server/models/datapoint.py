"""The measurement tables.

Google's API models time three ways, and a ``DataPoint`` carries exactly one of
them: ``ObservationTimeInterval`` for something accumulated over a window,
``ObservationSampleTime`` for something measured at an instant, and
``SessionTimeInterval`` for a window that bundles metrics and sub-intervals.
There is one table per shape, plus a landing zone for anything unclassifiable
and a child table for a session's segments.

Every value column is encrypted at rest; the identity and time columns are not,
so the natural key, the chart index and window queries still work in SQL. See
``server.models.encrypted``.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlmodel import Field, Index, SQLModel, UniqueConstraint

from server.models.encrypted import EncryptedDecimal, EncryptedJSON, EncryptedText
from server.models.util import civil_date_type, civil_type, utc_type


class DataPointBase(SQLModel):
    """Columns every measurement has, whatever its shape.

    Not a table: SQLModel only creates tables for ``table=True`` subclasses, so
    this defines the shared columns without a row of its own anywhere.
    """

    #: Surrogate key. The natural key is the unique constraint below; a single
    #: column exists so ``session_segments`` has something to point at without a
    #: three-column foreign key.
    id: int | None = Field(default=None, primary_key=True)

    health_user_id: str = Field(index=True)

    #: Google's data type name, verbatim and unvalidated. Not an enum: Google can
    #: add one at any time and an unrecognised value must be storable, not fatal.
    data_type: str = Field(index=True)

    #: Google's ``recordId``. The upsert target, so a correction to an interval
    #: overwrites rather than duplicating -- which assumes Google reuses the id
    #: across a correction rather than reissuing it.
    record_id: str

    #: Which platform recorded this point: Google's ``dataSource.platform``
    #: (``FITBIT``, ``HEALTH_KIT``, ...), or ``GOOGLE_HEALTH`` for a total Google
    #: computed across sources. Plaintext because reads filter on it: the same
    #: walk can arrive from a watch and a phone, and summing both counts it twice.
    #: Not an enum, for the same reason ``data_type`` is not.
    source_platform: str | None = Field(default=None)

    #: The absolute window, UTC. Nullable because a full-day activity omits
    #: ``physicalTimeInterval`` entirely -- for those, the civil columns are the
    #: only usable time.
    start_ts: datetime | None = Field(default=None, sa_type=utc_type())
    end_ts: datetime | None = Field(default=None, sa_type=utc_type())

    #: The same window as the user's clock showed it, derived from Google's
    #: ``startUtcOffset``/``endUtcOffset``. No timezone attached, deliberately.
    local_start: datetime | None = Field(default=None, sa_type=civil_type())
    local_end: datetime | None = Field(default=None, sa_type=civil_type())

    #: The local calendar date the dashboard aggregates on. "My Tuesday step
    #: count" means Tuesday where the user was standing. Indexed as part of the
    #: composite below, which is the shape every daily chart queries.
    civil_date: date | None = Field(default=None, sa_type=civil_date_type())

    #: The measurement, when it is a single number. Null for composite payloads.
    #: A ``Decimal``, not a float: step counts arrive as int64-in-a-string and
    #: masses as decimals, and a binary float cannot hold either exactly.
    value_numeric: Decimal | None = Field(default=None, sa_type=EncryptedDecimal())
    #: The unit that number is in, when Google states one ("kg", "m", "kcal").
    value_unit: str | None = Field(default=None, sa_type=EncryptedText())

    #: The union field from the dataPoint -- the type-specific payload itself.
    #: Nullable, and stated rather than inferred: ``Any`` reads as non-optional
    #: to SQLModel, and a point whose payload we could not identify should be
    #: recorded as having none rather than as an empty object, which would be a
    #: claim we cannot support.
    value: Any = Field(default=None, sa_type=EncryptedJSON(), nullable=True)

    #: The whole dataPoint as received. Not null on purpose -- a row that lost
    #: its source payload cannot be re-derived, and that is the one thing this
    #: column exists to prevent.
    raw: Any = Field(sa_type=EncryptedJSON(), nullable=False)

    #: Tombstone. ``operation: DELETE`` sets this; reads filter on it being
    #: null. A deletion that rewrote history would make models built on this
    #: data unreproducible.
    deleted_at: datetime | None = Field(default=None, sa_type=utc_type())

    fetched_at: datetime = Field(sa_type=utc_type(), nullable=False)


def _table_args(table: str) -> tuple[UniqueConstraint, Index]:
    """The natural key, and the index every chart query will want.

    The index is ``(health_user_id, data_type, civil_date)`` because that is the
    question the dashboard asks -- "this user's steps by local day" -- and a
    stored ``civil_date`` buys nothing if the read still has to scan.
    """
    return (
        UniqueConstraint(
            "health_user_id", "data_type", "record_id", name=f"uq_{table}_record"
        ),
        Index(
            f"ix_{table}_user_type_date", "health_user_id", "data_type", "civil_date"
        ),
    )


class ObservationTimeInterval(DataPointBase, table=True):
    """Accumulated over a window: steps, distance, floors, active minutes."""

    __tablename__ = "observation_time_intervals"
    __table_args__ = _table_args("observation_time_intervals")


class ObservationSampleTime(DataPointBase, table=True):
    """Measured at an instant: heart rate, weight, blood glucose, VO2 max."""

    __tablename__ = "observation_sample_times"
    __table_args__ = _table_args("observation_sample_times")


class SessionTimeInterval(DataPointBase, table=True):
    """A window bundling metrics and sub-intervals: sleep, exercise, nutrition.

    The summary metrics live in ``value``; the sub-intervals are rows in
    ``session_segments``.
    """

    __tablename__ = "session_time_intervals"
    __table_args__ = _table_args("session_time_intervals")


class UnknownDataPoint(DataPointBase, table=True):
    """Anything whose time structure could not be identified.

    Not a fallback so much as the arrival gate for every type we have not
    modelled yet: a point lands here with its payload intact and is promoted to
    a real table once a live example has shown what that table needs. It is why
    Google adding a data type is a row rather than an exception.
    """

    __tablename__ = "unknown_data_points"
    __table_args__ = _table_args("unknown_data_points")


class SessionSegment(SQLModel, table=True):
    """One sub-interval of a session: a sleep stage, a lap, a pause event.

    Google names these per data type (``Sleep.SleepStage``,
    ``Sleep.OutOfBedSegment``, ``Exercise.SplitSummary``,
    ``Exercise.ExerciseEvent``) and has no umbrella term, so the table is named
    generically and ``segment_type`` carries Google's name.
    """

    __tablename__ = "session_segments"

    id: int | None = Field(default=None, primary_key=True)

    #: The owning row in ``session_time_intervals``.
    session_id: int = Field(foreign_key="session_time_intervals.id", index=True)

    #: A ``SegmentType`` value. Stored as its string, so the column stays
    #: readable in psql and survives the enum gaining a member.
    segment_type: str = Field(index=True)

    #: What Google called this particular segment: "LIGHT", "DEEP", "REM",
    #: "AWAKE" for a sleep stage. Not an enum -- the vocabulary differs per data
    #: type and Google extends it. Encrypted: for a sleep stage, the label is the
    #: measurement.
    label: str | None = Field(default=None, sa_type=EncryptedText())

    start_ts: datetime | None = Field(default=None, sa_type=utc_type())
    end_ts: datetime | None = Field(default=None, sa_type=utc_type())
    local_start: datetime | None = Field(default=None, sa_type=civil_type())
    local_end: datetime | None = Field(default=None, sa_type=civil_type())

    #: The segment as received, for anything beyond its type and window.
    value: Any = Field(default=None, sa_type=EncryptedJSON(), nullable=True)
