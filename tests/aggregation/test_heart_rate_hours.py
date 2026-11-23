"""Heart-rate charts served from the stored hourly summaries.

The summaries exist to make long ranges cheap, not to change what is drawn. So
the main check is that a bucket built from hours is the bucket the samples
themselves would have given.
"""

import datetime as dt

import pytest

from server.aggregation.const import Resolution
from server.aggregation.series import SeriesAggregator
from server.aggregation.util import minutes_of
from server.models.datapoint import ObservationSampleTime, ObservationTimeInterval
from tests.aggregation.fakes import reader_over, row, stored_hour

START = dt.date(2026, 10, 29)
END = dt.date(2026, 11, 1)

#: Samples over two days, at two hours each, as (local time, bpm).
SAMPLES = [
    (dt.datetime(2026, 10, 29, 9, 0), 61),
    (dt.datetime(2026, 10, 29, 9, 30), 77),
    (dt.datetime(2026, 10, 29, 10, 15), 102),
    (dt.datetime(2026, 10, 30, 22, 5), 55),
    (dt.datetime(2026, 10, 30, 22, 6), 58),
    (dt.datetime(2026, 10, 30, 23, 59), 140),
]

#: Time-in-zone windows, as (local start, minutes, zone).
WINDOWS = [
    (dt.datetime(2026, 10, 29, 9, 0), 12.5, "FAT_BURN"),
    (dt.datetime(2026, 10, 29, 9, 40), 3, "CARDIO"),
    (dt.datetime(2026, 10, 30, 23, 50), 20, "PEAK"),
]


def hours_from(samples, windows):
    """What the rollup would store for these rows, built independently of it."""
    by_hour: dict[dt.datetime, tuple[list, dict]] = {}
    for local, bpm in samples:
        by_hour.setdefault(local.replace(minute=0), ([], {}))[0].append(bpm)
    for local, minutes, zone in windows:
        zones = by_hour.setdefault(local.replace(minute=0), ([], {}))[1]
        zones[zone] = zones.get(zone, 0) + minutes
    return [
        stored_hour(hour, found, zones) for hour, (found, zones) in by_hour.items()
    ]


def raw_reader():
    return reader_over(
        heart_rate=[row(local, numeric=bpm) for local, bpm in SAMPLES],
        time_in_heart_rate_zone=[
            row(local, minutes=minutes, value={"heartRateZoneType": zone})
            for local, minutes, zone in WINDOWS
        ],
    )


@pytest.mark.parametrize("resolution", [Resolution.HOUR, Resolution.DAY])
def test_stats_from_hours_match_stats_from_samples(resolution):
    from_samples = SeriesAggregator(raw_reader()).stats(
        ObservationSampleTime, "heart-rate", START, END, resolution
    )
    from_hours = SeriesAggregator(
        reader_over(hours=hours_from(SAMPLES, WINDOWS))
    ).heart_rate_stats(START, END, resolution)

    assert from_hours == from_samples


@pytest.mark.parametrize("resolution", [Resolution.HOUR, Resolution.DAY])
def test_zone_totals_from_hours_match_totals_from_windows(resolution):
    from_windows = SeriesAggregator(raw_reader()).category_totals(
        ObservationTimeInterval,
        "time-in-heart-rate-zone",
        START,
        END,
        resolution,
        "heartRateZoneType",
        minutes_of,
    )
    from_hours = SeriesAggregator(
        reader_over(hours=hours_from(SAMPLES, WINDOWS))
    ).heart_rate_zone_totals(START, END, resolution)

    assert from_hours == from_windows


def test_two_sources_in_one_hour_combine_exactly():
    """A mean of means would give 80; the samples' own mean is 70."""
    hour = dt.datetime(2026, 10, 29, 9)
    reader = reader_over(
        hours=[stored_hour(hour, [60, 60, 60]), stored_hour(hour, [100])]
    )

    [bucket] = SeriesAggregator(reader).heart_rate_stats(START, END, Resolution.HOUR)

    assert (bucket.min, bucket.avg, bucket.max, bucket.count) == (60, 70, 100, 4)


def test_an_hour_with_zone_time_but_no_samples_draws_no_heart_rate():
    reader = reader_over(
        hours=[stored_hour(dt.datetime(2026, 10, 29, 9), [], {"PEAK": 4})]
    )
    aggregator = SeriesAggregator(reader)

    assert aggregator.heart_rate_stats(START, END, Resolution.DAY) == []
    assert aggregator.heart_rate_zone_totals(START, END, Resolution.DAY) != []


@pytest.mark.parametrize("resolution", [Resolution.MINUTE, Resolution.HALF_HOUR])
def test_a_bucket_finer_than_an_hour_is_refused(resolution):
    """Hours cannot be cut into minutes; those spans must read the samples."""
    with pytest.raises(ValueError, match="cannot serve"):
        SeriesAggregator(reader_over()).heart_rate_stats(START, END, resolution)


def test_hours_count_towards_the_rows_read():
    reader = reader_over(hours=hours_from(SAMPLES, WINDOWS))

    SeriesAggregator(reader).heart_rate_stats(START, END, Resolution.DAY)

    assert reader.rows_read == 4
