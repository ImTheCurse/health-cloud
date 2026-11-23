"""Time series and per-day readings over the measurement tables.

Values are encrypted at rest, so every sum, mean and extreme here is computed in
Python over decrypted rows: the database narrows by user, type, civil date and
source, and nothing else.
"""

import datetime as dt
from collections import defaultdict
from collections.abc import Callable, Mapping

from server.aggregation.const import (
    AVERAGE_PLACES,
    READ_PLATFORMS,
    ROLLED_UP_RESOLUTIONS,
    Resolution,
)
from server.aggregation.schemas import (
    CategoryBucket,
    Number,
    Period,
    Reading,
    SedentaryDay,
    StatBucket,
    SumBucket,
    ZoneLimit,
    ZoneLimitsDay,
)
from server.aggregation.util import (
    at_path,
    bucket_of,
    number,
    tidy,
    tidy_or_none,
    window_minutes,
)
from server.db.measurements import Measurement, MeasurementRepository
from server.models.datapoint import DataPointBase
from server.rollup.hours import HeartRateHours, StoredHour


class MeasurementReader:
    """One user's live, single-source measurements, counting what it reads.

    Built per request: ``rows_read`` is what the request log reports, summary
    rows included.
    """

    def __init__(
        self,
        repository: MeasurementRepository,
        health_user_id: str,
        hours: HeartRateHours | None = None,
    ) -> None:
        self._repository = repository
        self._health_user_id = health_user_id
        self._hours = hours
        self.rows_read = 0

    def heart_rate_hours(self, start: dt.date, end: dt.date) -> list[StoredHour]:
        """The stored hourly heart-rate summaries with a civil date in the range."""
        if self._hours is None:
            raise RuntimeError("this reader was built without the hourly summaries")
        rows = self._hours.read(self._health_user_id, start, end, READ_PLATFORMS)
        self.rows_read += len(rows)
        return rows

    def read(
        self,
        table: type[DataPointBase],
        data_type: str,
        start: dt.date,
        end: dt.date,
        *,
        with_value: bool = False,
    ) -> list[Measurement]:
        rows = self._repository.measurements(
            table,
            health_user_id=self._health_user_id,
            data_type=data_type,
            start=start,
            end=end,
            with_value=with_value,
            platforms=READ_PLATFORMS,
        )
        self.rows_read += len(rows)
        return rows


class SeriesAggregator:
    """Buckets, totals and readings for every data type that is a plain series."""

    def __init__(self, reader: MeasurementReader) -> None:
        self._reader = reader

    def stats(
        self,
        table: type[DataPointBase],
        data_type: str,
        start: dt.date,
        end: dt.date,
        resolution: Resolution,
    ) -> list[StatBucket]:
        """Lowest, mean and highest sample in each bucket."""
        grouped: dict[dt.datetime, list[float]] = defaultdict(list)
        for row in self._reader.read(table, data_type, start, end):
            bucket = bucket_of(row, resolution)
            value = number(row.value_numeric)
            if bucket is not None and value is not None:
                grouped[bucket].append(value)
        return [
            StatBucket(
                start=bucket,
                min=tidy(min(values)),
                avg=round(sum(values) / len(values), AVERAGE_PLACES),
                max=tidy(max(values)),
                count=len(values),
            )
            for bucket, values in sorted(grouped.items())
        ]

    def sums(
        self,
        table: type[DataPointBase],
        data_type: str,
        start: dt.date,
        end: dt.date,
        resolution: Resolution,
        divisor: float = 1,
    ) -> list[SumBucket]:
        """The total of each bucket, divided by ``divisor`` to change unit."""
        totals: dict[dt.datetime, float] = defaultdict(float)
        for row in self._reader.read(table, data_type, start, end):
            bucket = bucket_of(row, resolution)
            value = number(row.value_numeric)
            if bucket is not None and value is not None:
                totals[bucket] += value
        return [
            SumBucket(start=bucket, total=tidy(total / divisor))
            for bucket, total in sorted(totals.items())
        ]

    def category_totals(
        self,
        table: type[DataPointBase],
        data_type: str,
        start: dt.date,
        end: dt.date,
        resolution: Resolution,
        category_key: str,
        measure: Callable[[Measurement], float | None],
    ) -> list[CategoryBucket]:
        """A total per category in each bucket.

        ``category_key`` names the payload field holding the category -- a zone,
        an activity level -- and ``measure`` says what one row contributes: its
        value, or the length of its window.
        """
        totals: dict[dt.datetime, dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        for row in self._reader.read(table, data_type, start, end, with_value=True):
            bucket = bucket_of(row, resolution)
            category = at_path(row.value, category_key)
            amount = measure(row)
            if bucket is None or not isinstance(category, str) or amount is None:
                continue
            totals[bucket][category] += amount
        return [
            CategoryBucket(
                start=bucket,
                totals={name: tidy(round(total, 2)) for name, total in sorted(by.items())},
            )
            for bucket, by in sorted(totals.items())
        ]

    def heart_rate_stats(
        self, start: dt.date, end: dt.date, resolution: Resolution
    ) -> list[StatBucket]:
        """``stats`` over the hourly summaries, for hourly or daily buckets.

        Each source's hour is a separate row; rows that share a bucket combine
        exactly, because each carries its sum and count rather than a mean.
        """
        _require_rolled_up(resolution)
        grouped: dict[dt.datetime, list[dict[str, float]]] = defaultdict(list)
        for hour in self._reader.heart_rate_hours(start, end):
            if hour.summary.get("count"):
                grouped[_hour_bucket(hour, resolution)].append(hour.summary)
        buckets = []
        for bucket, summaries in sorted(grouped.items()):
            count = sum(int(found["count"]) for found in summaries)
            total = sum(float(found["sum"]) for found in summaries)
            buckets.append(
                StatBucket(
                    start=bucket,
                    min=tidy(min(float(found["min"]) for found in summaries)),
                    avg=round(total / count, AVERAGE_PLACES),
                    max=tidy(max(float(found["max"]) for found in summaries)),
                    count=count,
                )
            )
        return buckets

    def heart_rate_zone_totals(
        self, start: dt.date, end: dt.date, resolution: Resolution
    ) -> list[CategoryBucket]:
        """``category_totals`` of time in zone, over the hourly summaries."""
        _require_rolled_up(resolution)
        totals: dict[dt.datetime, dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        for hour in self._reader.heart_rate_hours(start, end):
            zones = hour.summary.get("zone_minutes") or {}
            if not zones:
                continue
            bucket = totals[_hour_bucket(hour, resolution)]
            for zone, minutes in zones.items():
                bucket[zone] += float(minutes)
        return [
            CategoryBucket(
                start=bucket,
                totals={
                    name: tidy(round(total, 2)) for name, total in sorted(by.items())
                },
            )
            for bucket, by in sorted(totals.items())
        ]

    def readings(
        self,
        table: type[DataPointBase],
        data_type: str,
        start: dt.date,
        end: dt.date,
        fields: Mapping[str, str],
        divisors: Mapping[str, float] | None = None,
    ) -> list[Reading]:
        """The named payload fields of each row, as stored.

        ``fields`` maps each name the API returns to a dotted payload path. A
        field the payload lacks is left out of that reading rather than zeroed.
        """
        found = []
        for row in self._reader.read(table, data_type, start, end, with_value=True):
            if row.civil_date is None:
                continue
            values: dict[str, Number] = {}
            for name, path in fields.items():
                value = number(at_path(row.value, path))
                if value is not None:
                    values[name] = tidy(value / (divisors or {}).get(name, 1))
            if values:
                found.append(
                    Reading(date=row.civil_date, time=row.local_start, values=values)
                )
        return found

    def zone_limits(
        self, table: type[DataPointBase], data_type: str, start: dt.date, end: dt.date
    ) -> list[ZoneLimitsDay]:
        """Each day's heart-rate zones and the bpm range of each."""
        days = []
        for row in self._reader.read(table, data_type, start, end, with_value=True):
            zones = at_path(row.value, "heartRateZones")
            if row.civil_date is None or not isinstance(zones, list):
                continue
            days.append(
                ZoneLimitsDay(
                    date=row.civil_date,
                    zones=[
                        ZoneLimit(
                            zone=str(zone.get("heartRateZoneType")),
                            min_bpm=tidy_or_none(number(zone.get("minBeatsPerMinute"))),
                            max_bpm=tidy_or_none(number(zone.get("maxBeatsPerMinute"))),
                        )
                        for zone in zones
                        if isinstance(zone, dict)
                    ],
                )
            )
        return days

    def sedentary(
        self, table: type[DataPointBase], data_type: str, start: dt.date, end: dt.date
    ) -> list[SedentaryDay]:
        """Sedentary minutes per day, and the periods that make them up."""
        periods: dict[dt.date, list[Period]] = defaultdict(list)
        for row in self._reader.read(table, data_type, start, end):
            if row.civil_date is None:
                continue
            periods[row.civil_date].append(
                Period(
                    start=row.local_start,
                    end=row.local_end,
                    minutes=tidy(round(window_minutes(row.start_ts, row.end_ts), 2)),
                )
            )
        return [
            SedentaryDay(
                date=day,
                minutes=tidy(round(sum(p.minutes for p in found), 2)),
                periods=found,
            )
            for day, found in sorted(periods.items())
        ]


def _require_rolled_up(resolution: Resolution) -> None:
    if resolution not in ROLLED_UP_RESOLUTIONS:
        raise ValueError(f"the hourly summaries cannot serve {resolution} buckets")


def _hour_bucket(hour: StoredHour, resolution: Resolution) -> dt.datetime:
    """The bucket an hour's summary belongs to: itself, or its civil day."""
    if resolution is Resolution.DAY:
        return dt.datetime.combine(hour.civil_date, dt.time())
    return hour.hour_start
