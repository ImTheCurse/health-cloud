"""Column helpers shared by the table definitions.

Each shape comes as a *type* factory and, where a single table uses it directly,
a ``Column`` wrapper. The distinction matters: a ``Column`` object belongs to
exactly one table, so a field shared by several models through a base class must
pass ``sa_type=`` and let SQLModel build a fresh column per table. Passing
``sa_column=`` there fails with "Column object already assigned to Table".
"""

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Column, Date, DateTime, Numeric


def utc_type() -> DateTime:
    """Timezone-aware timestamp."""
    return DateTime(timezone=True)


def civil_type() -> DateTime:
    """Wall-clock timestamp with **no** timezone.

    The absence of an offset is the point. Google sends the user's local time
    alongside the absolute one, and storing it as ``timestamptz`` would attach
    UTC to it -- turning "my Tuesday" into Tuesday in UTC, which is the exact
    mistake the civil representation exists to prevent.
    """
    return DateTime(timezone=False)


def civil_date_type() -> Date:
    """The local calendar date a measurement belongs to.

    Stored rather than derived so the dashboard's daily ``GROUP BY`` can use an
    index instead of extracting from a timestamp on every read.
    """
    return Date()


def jsonb_type() -> JSONB:
    """``jsonb``, not ``json``.

    SQLModel re-exports generic ``JSON`` only, and ``json`` can carry neither a
    GIN index nor a value comparison without a cast. This module's import of
    ``JSONB`` and the one in ``notification.py`` are the only two places the
    project reaches past SQLModel into SQLAlchemy for a column type.

    ``none_as_null`` is not the default and has to be asked for. Without it
    SQLAlchemy stores Python ``None`` as the *JSON value* ``null``, which is a
    real value: it satisfies ``NOT NULL``, so a ``raw`` column declared not-null
    would silently accept a row with no payload, and "no payload" and "a payload
    that is null" would be indistinguishable on read. With it, ``None`` means SQL
    NULL, the constraint bites, and ``value`` records a genuine absence.
    """
    return JSONB(none_as_null=True)


def quantity_type() -> Numeric:
    """A scalar measurement, when the payload has one.

    ``Numeric`` rather than float: step counts arrive as int64-in-a-string and
    masses as decimals, and a binary float cannot hold either exactly. Null
    whenever the value is composite -- a nutrition log or an ECG waveform has no
    single number, and those live in ``value`` instead.
    """
    return Numeric()


def utc_column(*, nullable: bool = True) -> Column:
    """Timezone-aware timestamp, for a field only one table declares.

    sa_column bypasses SQLModel's nullability inference, so it is stated
    explicitly here.
    """
    return Column(utc_type(), nullable=nullable)
