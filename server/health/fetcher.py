"""Fetch one data type over one interval and write what comes back.

The single unit of work in the pipeline, and deliberately the only place that
knows how a measurement gets from Google into Postgres. Both callers share it:
the fetcher flow, reacting to a notification, and the backfill CLI, sweeping a
range nobody was notified about.

It is idempotent by construction -- every row is upserted on its natural key --
which is what makes the whole design tolerate at-least-once delivery. Re-running
it costs an HTTP call, never correctness, and that is the reason replay-based
durable execution was judged unnecessary.
"""

import datetime as dt
import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from decimal import Decimal

from loguru import logger
from sqlmodel import Session, select

from server.db.upsert import replace_segments, upsert_data_point, upsert_many
from server.health.client import HealthDataClient, within
from server.health.const import LIST_UNSUPPORTED, MAX_PAGES, UPSERT_BATCH_SIZE
from server.health.credentials import AccessTokens
from server.health.error import FetchError
from server.health.points import build
from server.health.util import parse_civil, parse_timestamp
from server.models.const import GOOGLE_HEALTH_PLATFORM, TimeStructure
from server.models.datapoint import DataPointBase, SessionTimeInterval, UnknownDataPoint
from server.models.user import User
from server.observability.util import hashed_log_id
from server.rollup.const import ROLLED_UP_TYPES
from server.rollup.hours import HourSpan


@dataclass(frozen=True)
class FetchResult:
    """What one unit of work did, for the log and for the flow's return value."""

    data_type: str
    written: int
    segments: int
    skipped: int
    #: Set when Google exposes no ``list`` for this type. Not a failure and not a
    #: success: the notification was handled as well as it can be today, and the
    #: measurement was not collected.
    unsupported: bool = False
    #: The local hours the written rows start in, for a type the hourly
    #: heart-rate summaries are built from. ``None`` for any other type, or when
    #: nothing was written.
    hours: HourSpan | None = None

    def __str__(self) -> str:
        if self.unsupported:
            return f"{self.data_type}: not readable with list, nothing collected"
        return f"{self.data_type}: {self.written} points, {self.segments} segments" + (
            f", {self.skipped} outside the window" if self.skipped else ""
        )


class Fetcher:
    """Reads an interval from Google and writes it to the database.

    Collaborators arrive through ``__init__``; nothing here reads settings, so a
    test constructs it with a fake transport and an in-memory repository.
    """

    def __init__(
        self,
        client: HealthDataClient,
        tokens: AccessTokens,
        session: Session,
    ) -> None:
        self._client = client
        self._tokens = tokens
        self._session = session

    def fetch_interval(
        self,
        *,
        user: User,
        data_type: str,
        start: dt.datetime,
        end: dt.datetime,
        deleted: bool = False,
    ) -> FetchResult:
        """Fetch ``data_type`` over ``[start, end)`` for ``user`` and store it.

        Args:
            deleted: the notification was an ``operation: DELETE``, so rows are
                tombstoned rather than removed. A deletion that rewrote history
                would make anything trained on this data unreproducible.

        Raises:
            TokenExpiredError: only re-consent will fix it; not worth a retry.
            FetchError: transient. The caller leaves the message unacknowledged
                and the work returns on the next run.

        A type Google exposes no ``list`` for returns a result marked
        ``unsupported`` rather than raising, so the message is acknowledged instead
        of cycling until ``max_deliver`` against an error that cannot clear.
        """
        if data_type == "floors":
            return self._fetch_floor_days(user, start, end)

        if data_type in LIST_UNSUPPORTED:
            # Checked here as well as in the client so no token is refreshed for a
            # read that cannot happen.
            logger.warning(
                "{} cannot be read with list; nothing collected for this notification",
                data_type,
            )
            return FetchResult(data_type, 0, 0, 0, unsupported=True)

        token = self._tokens.for_user(user)
        points = self._client.list_data_points(
            access_token=token, data_type=data_type, start=start, end=end
        )
        result = self._store(
            points,
            user=user,
            data_type=data_type,
            start=start,
            end=end,
            deleted=deleted,
        )
        logger.info(
            "fetched {} for user {}", result, hashed_log_id(user.health_user_id)
        )
        return result

    def backfill_window(
        self,
        *,
        user: User,
        data_type: str,
        start: dt.datetime,
        end: dt.datetime,
        on_day: Callable[[dt.date, int], None] | None = None,
    ) -> FetchResult:
        """Fetch ``[start, end)`` for a type Google cannot filter, in one pass.

        Without a filter, every request starts at "now" and pages backwards, so
        fetching day by day re-reads every newer day for each older one and the
        cost grows with the square of the window. One pass from now back to
        ``start`` reads each page once.

        Each day is committed as the pass moves past it, so a run that dies
        halfway keeps every finished day. The token is asked for before every
        page, because a long pass outlives the hour an access token lasts, and
        the page limit grows with the window.

        Args:
            on_day: called with each day and the rows written for it, once the
                day is committed. Progress for the CLI.
        """
        if data_type in LIST_UNSUPPORTED:
            return FetchResult(data_type, 0, 0, 0, unsupported=True)

        days = max(1, math.ceil((end - start) / dt.timedelta(days=1)))
        points = self._client.list_data_points(
            access_token=lambda: self._tokens.for_user(user),
            data_type=data_type,
            start=start,
            end=end,
            max_pages=MAX_PAGES * days,
        )
        result = self._store(
            points,
            user=user,
            data_type=data_type,
            start=start,
            end=end,
            on_day=on_day,
        )
        logger.info(
            "backfilled {} for user {}", result, hashed_log_id(user.health_user_id)
        )
        return result

    def _store(
        self,
        points: Iterable[dict],
        *,
        user: User,
        data_type: str,
        start: dt.datetime,
        end: dt.datetime,
        deleted: bool = False,
        on_day: Callable[[dt.date, int], None] | None = None,
    ) -> FetchResult:
        """Write the points that fall in the window.

        Without ``on_day``, everything commits once at the end, so a partially
        fetched notification is not half visible. With it, each day commits when
        the next point belongs to a different day, and once more at the end.
        """
        fetched_at = dt.datetime.now(dt.UTC)
        tombstone = fetched_at if deleted else None

        written = segments_written = skipped = 0
        first_local: dt.datetime | None = None
        last_local: dt.datetime | None = None
        pending: list[DataPointBase] = []
        current_day: dt.date | None = None
        day_written = 0

        def close_day() -> None:
            nonlocal written, day_written
            day_written += upsert_many(self._session, pending)
            pending.clear()
            self._session.commit()
            written += day_written
            if on_day is not None and current_day is not None:
                on_day(current_day, day_written)
            day_written = 0

        for point in points:
            row, segments = build(
                point,
                health_user_id=user.health_user_id,
                data_type=data_type,
                fetched_at=fetched_at,
                deleted_at=tombstone,
            )
            # An unfiltered type must be narrowed here rather than by Google.
            # Daily summaries carry only a civil date, not a physical timestamp.
            if not within(row.start_ts, start, end, row.civil_date):
                skipped += 1
                continue

            if data_type in ROLLED_UP_TYPES and row.local_start is not None:
                if first_local is None or row.local_start < first_local:
                    first_local = row.local_start
                if last_local is None or row.local_start > last_local:
                    last_local = row.local_start

            if on_day is not None:
                day = _day_of(row)
                if current_day is not None and day != current_day:
                    close_day()
                current_day = day

            if isinstance(row, SessionTimeInterval):
                # One at a time, because its segments need the id back.
                row_id = upsert_data_point(self._session, row)
                replace_segments(self._session, row_id, segments)
                segments_written += len(segments)
                day_written += 1
                continue

            pending.append(row)
            if len(pending) >= UPSERT_BATCH_SIZE:
                day_written += upsert_many(self._session, pending)
                pending.clear()

        close_day()
        hours = (
            HourSpan.around(first_local, last_local)
            if first_local is not None and last_local is not None
            else None
        )
        return FetchResult(data_type, written, segments_written, skipped, hours=hours)

    def _fetch_floor_days(
        self, user: User, start: dt.datetime, end: dt.datetime
    ) -> FetchResult:
        written = 0
        for day in _covered_days(start, end):
            written += self._fetch_floor_day(user, day)
        return FetchResult("floors", written, 0, 0)

    def _fetch_floor_day(self, user: User, day: dt.date) -> int:
        """Replace one day's aggregate, including when its last reading was deleted.

        The rollup is already reconciled across sources. Its civil day and source
        family are the natural key; there is no stable source-level record id.
        """
        token = self._tokens.for_user(user)
        buckets = self._client.daily_floor_rollup(access_token=token, day=day)
        fetched_at = dt.datetime.now(dt.UTC)
        record_id = f"rollup:all-sources:{day.isoformat()}"

        if buckets:
            bucket = buckets[0]
            civil_start = parse_civil(bucket.get("civilStartTime"))
            if civil_start is None or civil_start.date() != day:
                raise FetchError("floors rollup returned an unexpected civil day")
            value = bucket.get("floors")
            if value is not None:
                if not isinstance(value, dict):
                    raise FetchError("floors rollup value was not an object")
                try:
                    count = int(value["countSum"])
                except (KeyError, TypeError, ValueError) as error:
                    raise FetchError("floors rollup had no valid countSum") from error
                row = UnknownDataPoint(
                    health_user_id=user.health_user_id,
                    data_type="floors",
                    record_id=record_id,
                    source_platform=GOOGLE_HEALTH_PLATFORM,
                    civil_date=day,
                    value=value,
                    value_numeric=Decimal(count),
                    value_unit="count",
                    raw=bucket,
                    fetched_at=fetched_at,
                )
                upsert_many(self._session, [row])
                self._session.commit()
                return 1

        # An empty rollup after a DELETE means the old aggregate is no longer
        # current. Tombstone it, rather than leaving a stale daily total visible.
        existing = self._session.exec(
            select(UnknownDataPoint).where(
                UnknownDataPoint.health_user_id == user.health_user_id,
                UnknownDataPoint.data_type == "floors",
                UnknownDataPoint.record_id == record_id,
            )
        ).first()
        if existing is not None:
            existing.deleted_at = fetched_at
            existing.fetched_at = fetched_at
            self._session.add(existing)
        self._session.commit()
        return 0

    def fetch_pointer(self, user: User, pointer: dict) -> list[FetchResult]:
        """Fetch every interval named by one webhook change pointer.

        A pointer carries the data type, the operation, and one or more intervals
        -- the notification already says exactly what changed, so this is the
        cheapest correct set of calls.
        """
        data_type = pointer.get("dataType") or TimeStructure.UNKNOWN.value
        deleted = pointer.get("operation") == "DELETE"

        results = []
        for interval in pointer.get("intervals") or []:
            if data_type == "floors":
                civil = interval.get("civilIso8601TimeInterval") or {}
                start = parse_civil(civil.get("startTime"))
                end = parse_civil(civil.get("endTime"))
                if start is not None and end is not None:
                    results.append(self._fetch_floor_days(user, start, end))
                    continue

            window = _window(interval)
            if window is None:
                raise FetchError(
                    f"change pointer for {data_type} carried an unreadable interval"
                )
            start, end = window
            if data_type == "floors":
                # A physical-only pointer has no local date. Widen to cover any
                # civil day at UTC offsets of up to 14 hours.
                start -= dt.timedelta(hours=14)
                end += dt.timedelta(hours=14)
            results.append(
                self.fetch_interval(
                    user=user,
                    data_type=data_type,
                    start=start,
                    end=end,
                    deleted=deleted,
                )
            )
        return results


def _covered_days(start: dt.datetime, end: dt.datetime) -> list[dt.date]:
    """Civil dates touched by a half-open interval, excluding midnight at end."""
    if end <= start:
        raise FetchError("floors notification carried an empty or reversed interval")
    last = (end - dt.timedelta(microseconds=1)).date()
    day = start.date()
    days = []
    while day <= last:
        days.append(day)
        day += dt.timedelta(days=1)
    return days


def _window(interval: dict) -> tuple[dt.datetime, dt.datetime] | None:
    """The absolute window a change pointer's interval names.

    The physical interval is preferred because the query filter is in UTC. A
    full-day activity omits it, in which case the civil interval is read as UTC
    -- which can be off by a day's worth of hours at the edges, so the window is
    widened rather than risking a miss. Over-fetching costs a request;
    under-fetching loses a measurement.
    """
    physical = interval.get("physicalTimeInterval") or {}
    start = parse_timestamp(physical.get("startTime"))
    end = parse_timestamp(physical.get("endTime"))
    if start is not None and end is not None:
        return start, end

    civil = interval.get("civilIso8601TimeInterval") or {}
    start = parse_timestamp(civil.get("startTime"))
    end = parse_timestamp(civil.get("endTime"))
    if start is None or end is None:
        return None
    return start - dt.timedelta(hours=14), end + dt.timedelta(hours=14)


def _day_of(row: DataPointBase) -> dt.date | None:
    """The UTC day a row falls on, which is where a backfill commits."""
    if row.start_ts is not None:
        return row.start_ts.astimezone(dt.UTC).date()
    return row.civil_date
