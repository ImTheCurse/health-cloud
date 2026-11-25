"""Fetch a window nobody notified us about, one data type at a time.

Shared by ``backfill run`` on the command line and the scheduled
``backfill-recent`` flow, so both pick the same strategy for a type.

**Two strategies, by whether Google can filter the type by time.**

A filterable type is fetched a day at a time: each request asks Google for
exactly that day, so the cost is linear and a busy day stays well inside the
page limit. heart-rate alone is roughly 34,000 points, 7 pages, a day.

A type Google cannot filter always starts at "now" and pages backwards, so a day
at a time would re-read every newer day for each older one. Those take one pass
from now back to the start of the window instead, committing each day as the
pass leaves it, so a run interrupted halfway keeps every finished day. Rerunning
starts from "now" again and rewrites the same rows.
"""

import datetime as dt
from collections.abc import Callable

from server.health.const import FILTER_FIELDS, LIST_UNSUPPORTED
from server.health.fetcher import Fetcher, FetchResult
from server.models.user import User
from server.webhooks.const import DATA_TYPES, SYSTEM_EVENTS

#: Receives one line of progress at a time, for a caller that shows it.
Progress = Callable[[str], None]


def backfill_types() -> tuple[str, ...]:
    """Every subscribed type there is something to fetch for.

    The account events carry no data, and the types Google serves no ``list``
    for would only be skipped one by one -- except ``floors``, which has a
    rollup path of its own.
    """
    return tuple(
        data_type
        for data_type in DATA_TYPES
        if data_type not in SYSTEM_EVENTS
        and (data_type not in LIST_UNSUPPORTED or data_type == "floors")
    )


def backfill_type(
    fetcher: Fetcher,
    user: User,
    data_type: str,
    start: dt.datetime,
    end: dt.datetime,
    progress: Progress | None = None,
) -> FetchResult:
    """Fetch and store ``data_type`` over ``[start, end)`` for ``user``.

    Returns the totals, with the local hours written for a type the hourly
    heart-rate summaries are built from, so the caller can rebuild them.
    """
    if data_type in FILTER_FIELDS or data_type == "floors":
        return _by_day(fetcher, user, data_type, start, end, progress)
    return _in_one_pass(fetcher, user, data_type, start, end, progress)


def _by_day(
    fetcher: Fetcher,
    user: User,
    data_type: str,
    start: dt.datetime,
    end: dt.datetime,
    progress: Progress | None,
) -> FetchResult:
    """One request per day, for a type Google filters by time."""
    written = segments = skipped = 0
    hours = None
    # Floor rollups are civil-day aggregates. Align their windows to midnight so
    # adjacent backfill days do not fetch the same day twice.
    if data_type == "floors":
        start = dt.datetime.combine(start.date(), dt.time(), tzinfo=dt.UTC)
    for day_start, day_end in _days(start, end):
        result = fetcher.fetch_interval(
            user=user, data_type=data_type, start=day_start, end=day_end
        )
        if result.unsupported:
            return result
        written += result.written
        segments += result.segments
        skipped += result.skipped
        if result.hours is not None:
            hours = result.hours.union(hours)
        if progress is not None:
            progress(f"  {data_type} {day_start.date()}: {result.written} points")
    if progress is not None:
        progress(f"  {data_type}: {written} points, {segments} segments in total")
    return FetchResult(data_type, written, segments, skipped, hours=hours)


def _in_one_pass(
    fetcher: Fetcher,
    user: User,
    data_type: str,
    start: dt.datetime,
    end: dt.datetime,
    progress: Progress | None,
) -> FetchResult:
    """One backward pass over the whole window, for a type Google cannot filter."""

    def report(day: dt.date, written: int) -> None:
        if progress is not None:
            progress(f"  {data_type} {day}: {written} points")

    result = fetcher.backfill_window(
        user=user, data_type=data_type, start=start, end=end, on_day=report
    )
    if progress is not None:
        if result.unsupported:
            progress(f"  {data_type}: not readable with list, skipped")
        else:
            progress(
                f"  {data_type}: {result.written} points, "
                f"{result.segments} segments in total"
            )
    return result


def _days(
    start: dt.datetime, end: dt.datetime
) -> list[tuple[dt.datetime, dt.datetime]]:
    """``[start, end)`` split into windows of at most a day, oldest first."""
    windows = []
    cursor = start
    while cursor < end:
        following = min(cursor + dt.timedelta(days=1), end)
        windows.append((cursor, following))
        cursor = following
    return windows
