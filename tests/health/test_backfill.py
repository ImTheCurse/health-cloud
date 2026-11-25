"""Which strategy a backfill uses for a type, and what it adds up."""

import datetime as dt

from server.health.backfill import backfill_type
from server.health.fetcher import FetchResult
from server.rollup.hours import HourSpan

START = dt.datetime(2026, 11, 24, 12, tzinfo=dt.UTC)
END = dt.datetime(2026, 11, 26, tzinfo=dt.UTC)
NINE = dt.datetime(2026, 11, 25, 9)


class FakeFetcher:
    def __init__(self) -> None:
        self.intervals: list[tuple[dt.datetime, dt.datetime]] = []
        self.passes: list[tuple[dt.datetime, dt.datetime]] = []

    def fetch_interval(self, *, user, data_type, start, end):
        self.intervals.append((start, end))
        return FetchResult(data_type, 2, 1, 0)

    def backfill_window(self, *, user, data_type, start, end, on_day=None):
        self.passes.append((start, end))
        return FetchResult(
            data_type, 5, 0, 3, hours=HourSpan(NINE, NINE + dt.timedelta(hours=1))
        )


def test_a_filterable_type_is_fetched_a_day_at_a_time():
    fetcher = FakeFetcher()

    result = backfill_type(fetcher, None, "steps", START, END)  # type: ignore[arg-type]

    assert fetcher.intervals == [
        (START, START + dt.timedelta(days=1)),
        (START + dt.timedelta(days=1), END),
    ]
    assert (result.written, result.segments) == (4, 2)


def test_an_unfilterable_type_is_fetched_in_one_pass():
    fetcher = FakeFetcher()

    result = backfill_type(fetcher, None, "exercise", START, END)  # type: ignore[arg-type]

    assert fetcher.passes == [(START, END)]
    assert fetcher.intervals == []
    assert result.hours == HourSpan(NINE, NINE + dt.timedelta(hours=1))


def test_progress_is_reported_when_asked_for():
    lines: list[str] = []

    backfill_type(FakeFetcher(), None, "steps", START, END, progress=lines.append)  # type: ignore[arg-type]

    assert lines[-1] == "  steps: 4 points, 2 segments in total"
