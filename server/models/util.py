"""Column helpers shared by the table definitions.

Each shape comes as a *type* factory and, where a single table uses it directly,
a ``Column`` wrapper. The distinction matters: a ``Column`` object belongs to
exactly one table, so a field shared by several models through a base class must
pass ``sa_type=`` and let SQLModel build a fresh column per table. Passing
``sa_column=`` there fails with "Column object already assigned to Table".
"""

from sqlmodel import Column, Date, DateTime


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


def utc_column(*, nullable: bool = True) -> Column:
    """Timezone-aware timestamp, for a field only one table declares.

    sa_column bypasses SQLModel's nullability inference, so it is stated
    explicitly here.
    """
    return Column(utc_type(), nullable=nullable)
