"""Stored summaries of the measurement tables.

A summary is derived, never received: it is rebuilt from the raw rows it
summarises, so it can always be thrown away and written again. Its values are
health data all the same, so they are encrypted like the rows they come from.
"""

import datetime as dt
from typing import Any

from sqlmodel import Field, Index, SQLModel, UniqueConstraint

from server.models.encrypted import EncryptedJSON
from server.models.util import civil_date_type, civil_type, utc_type


class HeartRateHour(SQLModel, table=True):
    """One local hour of heart rate, for one user and one source.

    Long chart ranges read these instead of the samples: 90 days is about 2,000
    rows rather than about 3 million. The summary is one encrypted document, so
    a row costs one decryption whatever it holds.
    """

    __tablename__ = "heart_rate_hours"
    __table_args__ = (
        UniqueConstraint(
            "health_user_id",
            "source_platform",
            "hour_start",
            name="uq_heart_rate_hours_hour",
        ),
        Index("ix_heart_rate_hours_user_date", "health_user_id", "civil_date"),
    )

    id: int | None = Field(default=None, primary_key=True)
    health_user_id: str
    #: The platform the summarised rows came from. Plaintext for the same reason
    #: as on a measurement: reads keep only some sources.
    source_platform: str
    #: The start of the hour on the user's clock.
    hour_start: dt.datetime = Field(sa_type=civil_type(), nullable=False)
    #: The local date of ``hour_start``, which is what a daily chart groups on.
    civil_date: dt.date = Field(sa_type=civil_date_type(), nullable=False)
    #: ``count``, ``sum``, ``min`` and ``max`` of the heart-rate samples, the
    #: first two so that hours combine into an exact daily mean, and
    #: ``zone_minutes``: minutes in each heart-rate zone, from Google's own
    #: time-in-zone windows. The four sample figures are absent from an hour
    #: with zone time but no samples.
    summary: Any = Field(sa_type=EncryptedJSON(), nullable=False)
    built_at: dt.datetime = Field(sa_type=utc_type(), nullable=False)
