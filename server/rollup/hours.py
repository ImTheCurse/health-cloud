"""Hourly heart-rate summaries: rebuilding them, and reading them back.

**Rebuilt, never adjusted.** An hour's row is recomputed from every live sample
and time-in-zone window in that hour, then replaces whatever was there. Running a
rebuild twice therefore leaves the same rows, a late or corrected sample is
picked up by rebuilding its hour, and a tombstoned sample drops out of it.

Values are encrypted, so the work is done in Python over decrypted rows, like
every other read. The database narrows by user, civil date and local start,
which are plaintext.
"""

import datetime as dt
from collections import defaultdict
from collections.abc import Callable, Collection, Iterator
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session, col

from server.aggregation.util import at_path, number, window_minutes
from server.models.datapoint import (
    DataPointBase,
    ObservationSampleTime,
    ObservationTimeInterval,
)
from server.models.rollup import HeartRateHour
from server.rollup.const import HEART_RATE, REBUILD_CHUNK, TIME_IN_ZONE, ZONE_KEY

HOUR = dt.timedelta(hours=1)


def hour_of(local: dt.datetime) -> dt.datetime:
    """The start of the local hour ``local`` falls in."""
    return local.replace(minute=0, second=0, microsecond=0)


@dataclass(frozen=True)
class HourSpan:
    """Whole local hours, ``[start, end)``: what a rebuild covers."""

    start: dt.datetime
    end: dt.datetime

    @classmethod
    def around(cls, first: dt.datetime, last: dt.datetime) -> "HourSpan":
        """The hours from the one ``first`` is in to the one ``last`` is in."""
        return cls(hour_of(first), hour_of(last) + HOUR)

    def union(self, other: "HourSpan | None") -> "HourSpan":
        if other is None:
            return self
        return HourSpan(min(self.start, other.start), max(self.end, other.end))

    def chunks(self, size: dt.timedelta = REBUILD_CHUNK) -> Iterator["HourSpan"]:
        """The span cut into pieces of at most ``size``, oldest first."""
        cursor = self.start
        while cursor < self.end:
            following = min(cursor + size, self.end)
            yield HourSpan(cursor, following)
            cursor = following


@dataclass
class _Hour:
    """One hour's figures while they are being added up."""

    count: int = 0
    total: float = 0.0
    lowest: float | None = None
    highest: float | None = None
    zone_minutes: dict[str, float] = field(default_factory=lambda: defaultdict(float))

    def add_sample(self, bpm: float) -> None:
        self.count += 1
        self.total += bpm
        self.lowest = bpm if self.lowest is None else min(self.lowest, bpm)
        self.highest = bpm if self.highest is None else max(self.highest, bpm)

    def summary(self) -> dict[str, Any]:
        found: dict[str, Any] = {}
        if self.count:
            found |= {
                "count": self.count,
                "sum": self.total,
                "min": self.lowest,
                "max": self.highest,
            }
        found["zone_minutes"] = dict(sorted(self.zone_minutes.items()))
        return found


@dataclass(frozen=True)
class StoredHour:
    """One summary as read back, decrypted."""

    hour_start: dt.datetime
    civil_date: dt.date
    summary: dict[str, Any]


class HeartRateHours:
    """The ``heart_rate_hours`` table, bound to one session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def rebuild(self, health_user_id: str, span: HourSpan) -> int:
        """Replace one user's summaries for ``span`` with fresh ones.

        Returns:
            How many hour rows were written.

        Runs in the caller's transaction and does not commit, so a reader sees
        either the old hours or the new ones.
        """
        hours: dict[tuple[str, dt.datetime], _Hour] = defaultdict(_Hour)

        for platform, local_start, value in self._rows(
            ObservationSampleTime, HEART_RATE, health_user_id, span, sample=True
        ):
            bpm = number(value)
            if bpm is not None:
                hours[(platform, hour_of(local_start))].add_sample(bpm)

        for platform, local_start, (start_ts, end_ts, payload) in self._rows(
            ObservationTimeInterval, TIME_IN_ZONE, health_user_id, span, sample=False
        ):
            zone = at_path(payload, ZONE_KEY)
            if isinstance(zone, str):
                hours[(platform, hour_of(local_start))].zone_minutes[zone] += (
                    window_minutes(start_ts, end_ts)
                )

        table = HeartRateHour.__table__  # type: ignore[attr-defined]
        self._session.execute(
            delete(table)
            .where(table.c.health_user_id == health_user_id)
            .where(table.c.hour_start >= span.start)
            .where(table.c.hour_start < span.end)
        )
        if not hours:
            return 0

        built_at = dt.datetime.now(dt.UTC)
        self._session.execute(
            insert(table).values(
                [
                    {
                        "health_user_id": health_user_id,
                        "source_platform": platform,
                        "hour_start": hour,
                        "civil_date": hour.date(),
                        # Bound through the column type, which encrypts it.
                        "summary": figures.summary(),
                        "built_at": built_at,
                    }
                    for (platform, hour), figures in sorted(hours.items())
                ]
            )
        )
        return len(hours)

    def rebuild_in_chunks(
        self,
        health_user_id: str,
        span: HourSpan,
        on_chunk: Callable[[HourSpan, int], None] | None = None,
    ) -> int:
        """Rebuild ``span`` a day at a time, committing each day.

        A long rebuild interrupted part way keeps every finished day, and a
        repeat redoes the rest.
        """
        written = 0
        for chunk in span.chunks():
            count = self.rebuild(health_user_id, chunk)
            self._session.commit()
            written += count
            if on_chunk is not None:
                on_chunk(chunk, count)
        return written

    def read(
        self,
        health_user_id: str,
        start: dt.date,
        end: dt.date,
        platforms: Collection[str],
    ) -> list[StoredHour]:
        """Summaries whose civil date is in ``[start, end)``, oldest first."""
        statement = (
            select(
                col(HeartRateHour.hour_start),
                col(HeartRateHour.civil_date),
                col(HeartRateHour.summary),
            )
            .where(col(HeartRateHour.health_user_id) == health_user_id)
            .where(col(HeartRateHour.civil_date) >= start)
            .where(col(HeartRateHour.civil_date) < end)
            .where(col(HeartRateHour.source_platform).in_(platforms))
            .order_by(col(HeartRateHour.hour_start))
        )
        return [StoredHour(*row) for row in self._session.execute(statement)]

    def _rows(
        self,
        table: type[DataPointBase],
        data_type: str,
        health_user_id: str,
        span: HourSpan,
        *,
        sample: bool,
    ) -> Iterator[tuple[str, dt.datetime, Any]]:
        """Live rows of one type starting in ``span``: platform, local start, value.

        The value is the number for a sample, and the window with its payload
        for a time-in-zone row. The civil date bounds the read to the chart
        index; the local start then trims it to the span's exact hours.
        """
        value: list[Any] = (
            [col(table.value_numeric)]
            if sample
            else [col(table.start_ts), col(table.end_ts), col(table.value)]
        )
        statement = (
            select(col(table.source_platform), col(table.local_start), *value)
            .where(col(table.health_user_id) == health_user_id)
            .where(col(table.data_type) == data_type)
            .where(col(table.civil_date) >= span.start.date())
            .where(col(table.civil_date) <= (span.end - dt.timedelta.resolution).date())
            .where(col(table.local_start) >= span.start)
            .where(col(table.local_start) < span.end)
            .where(col(table.deleted_at).is_(None))
        )
        for row in self._session.execute(statement):
            platform, local_start, *rest = row
            if platform is None or local_start is None:
                continue
            yield platform, local_start, rest[0] if sample else tuple(rest)
