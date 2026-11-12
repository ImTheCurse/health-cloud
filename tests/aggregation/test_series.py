"""Buckets, totals and readings, computed in Python over decrypted rows."""

import datetime as dt

from server.aggregation.const import READ_PLATFORMS, Resolution
from server.aggregation.series import SeriesAggregator
from server.aggregation.util import minutes_of, value_of
from server.models.datapoint import (
    ObservationSampleTime,
    ObservationTimeInterval,
    UnknownDataPoint,
)
from tests.aggregation.fakes import reader_over, row

DAY = dt.date(2026, 10, 30)
NEXT = DAY + dt.timedelta(days=1)


def at(hour, minute=0, second=0, day=DAY):
    return dt.datetime.combine(day, dt.time(hour, minute, second))


def test_samples_are_bucketed_by_local_minute():
    reader = reader_over(
        heart_rate=[
            row(at(9, 0, 5), numeric=60),
            row(at(9, 0, 50), numeric=70),
            row(at(9, 1, 10), numeric=80),
        ]
    )

    buckets = SeriesAggregator(reader).stats(
        ObservationSampleTime, "heart-rate", DAY, NEXT, Resolution.MINUTE
    )

    assert [(b.start, b.min, b.avg, b.max, b.count) for b in buckets] == [
        (at(9, 0), 60, 65.0, 70, 2),
        (at(9, 1), 80, 80.0, 80, 1),
    ]


def test_buckets_floor_to_their_width():
    reader = reader_over(heart_rate=[row(at(9, 29), numeric=60), row(at(9, 31), numeric=70)])

    buckets = SeriesAggregator(reader).stats(
        ObservationSampleTime, "heart-rate", DAY, NEXT, Resolution.HALF_HOUR
    )

    assert [b.start for b in buckets] == [at(9, 0), at(9, 30)]


def test_the_average_keeps_one_decimal():
    reader = reader_over(heart_rate=[row(at(9), numeric=n) for n in (60, 61, 61)])

    [bucket] = SeriesAggregator(reader).stats(
        ObservationSampleTime, "heart-rate", DAY, NEXT, Resolution.DAY
    )

    assert bucket.avg == 60.7


def test_a_daily_bucket_keys_on_the_civil_date():
    """An interval stored on Friday stays Friday's even if its clock says
    otherwise: the civil date is the day the dashboard groups by."""
    reader = reader_over(steps=[row(at(23, 50), numeric=100, civil_date=DAY)])

    [bucket] = SeriesAggregator(reader).sums(
        ObservationTimeInterval, "steps", DAY, NEXT, Resolution.DAY
    )

    assert bucket.start == at(0)
    assert bucket.total == 100


def test_steps_are_summed_per_bucket_as_whole_numbers():
    reader = reader_over(
        steps=[row(at(9, 1), numeric="412"), row(at(9, 7), numeric="88"), row(at(10), numeric=5)]
    )

    buckets = SeriesAggregator(reader).sums(
        ObservationTimeInterval, "steps", DAY, NEXT, Resolution.HOUR
    )

    assert [(b.start, b.total) for b in buckets] == [(at(9), 500), (at(10), 5)]
    assert isinstance(buckets[0].total, int)


def test_a_divisor_changes_the_unit():
    reader = reader_over(distance=[row(at(9), numeric=1500), row(at(9, 5), numeric=250)])

    [bucket] = SeriesAggregator(reader).sums(
        ObservationTimeInterval, "distance", DAY, NEXT, Resolution.DAY, divisor=1000
    )

    assert bucket.total == 1.75


def test_category_minutes_come_from_window_lengths():
    reader = reader_over(
        activity_level=[
            row(at(9), minutes=10, value={"activityLevelType": "SEDENTARY"}),
            row(at(9, 10), minutes=5, value={"activityLevelType": "VERY_ACTIVE"}),
            row(at(9, 15), minutes=2.5, value={"activityLevelType": "SEDENTARY"}),
        ]
    )

    [bucket] = SeriesAggregator(reader).category_totals(
        ObservationTimeInterval,
        "activity-level",
        DAY,
        NEXT,
        Resolution.DAY,
        "activityLevelType",
        minutes_of,
    )

    assert bucket.totals == {"SEDENTARY": 12.5, "VERY_ACTIVE": 5}


def test_category_totals_can_come_from_each_rows_value():
    reader = reader_over(
        active_zone_minutes=[
            row(at(9), numeric=2, value={"heartRateZone": "CARDIO"}),
            row(at(9, 1), numeric=1, value={"heartRateZone": "FAT_BURN"}),
            row(at(9, 2), numeric=2, value={"heartRateZone": "CARDIO"}),
        ]
    )

    [bucket] = SeriesAggregator(reader).category_totals(
        ObservationTimeInterval,
        "active-zone-minutes",
        DAY,
        NEXT,
        Resolution.DAY,
        "heartRateZone",
        value_of,
    )

    assert bucket.totals == {"CARDIO": 4, "FAT_BURN": 1}


def test_readings_pick_named_fields_and_skip_missing_ones():
    reader = reader_over(
        daily_oxygen_saturation=[
            row(
                civil_date=DAY,
                value={"averagePercentage": 95.5, "lowerBoundPercentage": 93.0},
            )
        ]
    )

    [reading] = SeriesAggregator(reader).readings(
        UnknownDataPoint,
        "daily-oxygen-saturation",
        DAY,
        NEXT,
        {"average": "averagePercentage", "upper": "upperBoundPercentage"},
    )

    assert reading.date == DAY
    assert reading.time is None
    assert reading.values == {"average": 95.5}


def test_readings_follow_nested_paths_and_divisors():
    reader = reader_over(
        height=[row(at(8), value={"heightMillimeters": "1800"})],
        respiratory_rate_sleep_summary=[
            row(at(7), value={"fullSleepStats": {"breathsPerMinute": 14.2}})
        ],
    )
    series = SeriesAggregator(reader)

    [height] = series.readings(
        ObservationSampleTime,
        "height",
        DAY,
        NEXT,
        {"meters": "heightMillimeters"},
        {"meters": 1000},
    )
    [night] = series.readings(
        ObservationSampleTime,
        "respiratory-rate-sleep-summary",
        DAY,
        NEXT,
        {"full": "fullSleepStats.breathsPerMinute"},
    )

    assert height.values == {"meters": 1.8}
    assert night.values == {"full": 14.2}
    assert night.time == at(7)


def test_zone_limits_are_read_per_day():
    zones = [
        {"heartRateZoneType": "LIGHT", "minBeatsPerMinute": "98", "maxBeatsPerMinute": "121"},
        {"heartRateZoneType": "PEAK", "minBeatsPerMinute": "169"},
    ]
    reader = reader_over(daily_heart_rate_zones=[row(civil_date=DAY, value={"heartRateZones": zones})])

    [day] = SeriesAggregator(reader).zone_limits(
        UnknownDataPoint, "daily-heart-rate-zones", DAY, NEXT
    )

    assert [(z.zone, z.min_bpm, z.max_bpm) for z in day.zones] == [
        ("LIGHT", 98, 121),
        ("PEAK", 169, None),
    ]


def test_sedentary_minutes_add_up_their_periods():
    reader = reader_over(
        sedentary_period=[row(at(9), minutes=30), row(at(13), minutes=45)]
    )

    [day] = SeriesAggregator(reader).sedentary(
        ObservationTimeInterval, "sedentary-period", DAY, NEXT
    )

    assert day.minutes == 75
    assert [(p.start, p.minutes) for p in day.periods] == [(at(9), 30), (at(13), 45)]


def test_every_read_keeps_to_the_chosen_sources_and_is_counted():
    reader = reader_over(heart_rate=[row(at(9), numeric=60), row(at(10), numeric=61)])

    SeriesAggregator(reader).stats(
        ObservationSampleTime, "heart-rate", DAY, NEXT, Resolution.DAY
    )

    assert reader._repository.calls[0]["platforms"] == READ_PLATFORMS  # type: ignore[attr-defined]
    assert reader.rows_read == 2
