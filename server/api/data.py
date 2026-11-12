"""Read routes: the signed-in user's measurements, shaped for charts.

Grouped by what they measure rather than by table, and named after Google's data
types. Every route needs a session, reads only that user's rows, and keeps to the
sources in ``READ_PLATFORMS``. Ranges are civil dates, half-open: ``end`` is
excluded.
"""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from server.aggregation.const import (
    MAX_DAYS,
    MAX_RANGE_DAYS,
    MILLIMETERS_PER_METER,
    Resolution,
)
from server.aggregation.logs import (
    EXERCISE,
    HYDRATION_LOG,
    NUTRITION_LOG,
    LogAggregator,
)
from server.aggregation.schemas import (
    CategorySeries,
    Exercise,
    Hydration,
    Nutrition,
    Readings,
    Sedentary,
    Sleep,
    StatSeries,
    SumSeries,
    ZoneLimits,
)
from server.aggregation.series import MeasurementReader, SeriesAggregator
from server.aggregation.sleep import SLEEP, SleepAggregator
from server.aggregation.util import minutes_of, value_of
from server.api.auth import current_user
from server.db.session import SessionDep
from server.models.datapoint import (
    ObservationSampleTime,
    ObservationTimeInterval,
    UnknownDataPoint,
)
from server.models.user import User
from server.observability.context import RequestLog, RequestLogDep
from server.providers import build_measurement_reader

router = APIRouter(prefix="/data", tags=["data"])


def get_reader(
    session: SessionDep, user: Annotated[User, Depends(current_user)]
) -> MeasurementReader:
    """The signed-in user's measurements. A 401 without a session."""
    return build_measurement_reader(session, user.health_user_id)


Reader = Annotated[MeasurementReader, Depends(get_reader)]
Start = Annotated[dt.date, Query(description="first civil date, included")]
End = Annotated[dt.date, Query(description="last civil date, excluded")]
Bucket = Annotated[Resolution, Query(description="bucket width")]


def checked_range(start: dt.date, end: dt.date, max_days: int) -> None:
    """Refuse an empty, reversed or oversized range with a 422."""
    if end <= start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="end must be after start",
        )
    if (end - start).days > max_days:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"range is limited to {max_days} days here",
        )


def record(
    log: RequestLog,
    reader: MeasurementReader,
    data_type: str,
    start: dt.date,
    end: dt.date,
) -> None:
    """One event per read: what was asked for and how much it took, no values."""
    log.add_event(
        "measurements_read",
        data_type=data_type,
        days=(end - start).days,
        rows=reader.rows_read,
    )


# --- heart rate ----------------------------------------------------------


@router.get("/heart-rate")
def heart_rate(
    reader: Reader,
    log: RequestLogDep,
    start: Start,
    end: End,
    resolution: Bucket = Resolution.DAY,
) -> StatSeries:
    checked_range(start, end, MAX_DAYS[resolution])
    buckets = SeriesAggregator(reader).stats(
        ObservationSampleTime, "heart-rate", start, end, resolution
    )
    record(log, reader, "heart-rate", start, end)
    return StatSeries(
        data_type="heart-rate", unit="bpm", resolution=resolution, buckets=buckets
    )


@router.get("/heart-rate/resting")
def resting_heart_rate(
    reader: Reader, log: RequestLogDep, start: Start, end: End
) -> Readings:
    return _readings(
        reader,
        log,
        "daily-resting-heart-rate",
        start,
        end,
        {"bpm": "beatsPerMinute"},
    )


@router.get("/heart-rate/zones")
def heart_rate_zones(
    reader: Reader, log: RequestLogDep, start: Start, end: End
) -> ZoneLimits:
    checked_range(start, end, MAX_RANGE_DAYS)
    days = SeriesAggregator(reader).zone_limits(
        UnknownDataPoint, "daily-heart-rate-zones", start, end
    )
    record(log, reader, "daily-heart-rate-zones", start, end)
    return ZoneLimits(data_type="daily-heart-rate-zones", days=days)


@router.get("/heart-rate/time-in-zone")
def time_in_heart_rate_zone(
    reader: Reader,
    log: RequestLogDep,
    start: Start,
    end: End,
    resolution: Bucket = Resolution.DAY,
) -> CategorySeries:
    return _categories(
        reader,
        log,
        "time-in-heart-rate-zone",
        start,
        end,
        resolution,
        category_key="heartRateZoneType",
        by_window=True,
    )


@router.get("/heart-rate/variability")
def heart_rate_variability(
    reader: Reader,
    log: RequestLogDep,
    start: Start,
    end: End,
    resolution: Bucket = Resolution.DAY,
) -> StatSeries:
    checked_range(start, end, MAX_DAYS[resolution])
    buckets = SeriesAggregator(reader).stats(
        ObservationSampleTime, "heart-rate-variability", start, end, resolution
    )
    record(log, reader, "heart-rate-variability", start, end)
    return StatSeries(
        data_type="heart-rate-variability",
        unit="ms",
        resolution=resolution,
        buckets=buckets,
    )


@router.get("/heart-rate/variability/daily")
def daily_heart_rate_variability(
    reader: Reader, log: RequestLogDep, start: Start, end: End
) -> Readings:
    return _readings(
        reader,
        log,
        "daily-heart-rate-variability",
        start,
        end,
        {
            "average_ms": "averageHeartRateVariabilityMilliseconds",
            "deep_sleep_rmssd_ms": (
                "deepSleepRootMeanSquareOfSuccessiveDifferencesMilliseconds"
            ),
            "entropy": "entropy",
            "non_rem_heart_rate_bpm": "nonRemHeartRateBeatsPerMinute",
        },
    )


# --- oxygen saturation and breathing -------------------------------------


@router.get("/oxygen-saturation")
def oxygen_saturation(
    reader: Reader,
    log: RequestLogDep,
    start: Start,
    end: End,
    resolution: Bucket = Resolution.DAY,
) -> StatSeries:
    checked_range(start, end, MAX_DAYS[resolution])
    buckets = SeriesAggregator(reader).stats(
        ObservationSampleTime, "oxygen-saturation", start, end, resolution
    )
    record(log, reader, "oxygen-saturation", start, end)
    return StatSeries(
        data_type="oxygen-saturation",
        unit="percent",
        resolution=resolution,
        buckets=buckets,
    )


@router.get("/oxygen-saturation/daily")
def daily_oxygen_saturation(
    reader: Reader, log: RequestLogDep, start: Start, end: End
) -> Readings:
    return _readings(
        reader,
        log,
        "daily-oxygen-saturation",
        start,
        end,
        {
            "average_percent": "averagePercentage",
            "lower_bound_percent": "lowerBoundPercentage",
            "upper_bound_percent": "upperBoundPercentage",
            "standard_deviation_percent": "standardDeviationPercentage",
        },
    )


@router.get("/respiratory-rate")
def respiratory_rate(
    reader: Reader, log: RequestLogDep, start: Start, end: End
) -> Readings:
    """Breaths per minute over each night, overall and per sleep stage."""
    return _readings(
        reader,
        log,
        "respiratory-rate-sleep-summary",
        start,
        end,
        {
            "full_sleep": "fullSleepStats.breathsPerMinute",
            "deep_sleep": "deepSleepStats.breathsPerMinute",
            "light_sleep": "lightSleepStats.breathsPerMinute",
            "rem_sleep": "remSleepStats.breathsPerMinute",
        },
        table=ObservationSampleTime,
    )


@router.get("/respiratory-rate/daily")
def daily_respiratory_rate(
    reader: Reader, log: RequestLogDep, start: Start, end: End
) -> Readings:
    return _readings(
        reader,
        log,
        "daily-respiratory-rate",
        start,
        end,
        {"breaths_per_minute": "breathsPerMinute"},
    )


# --- sleep -----------------------------------------------------------------


@router.get("/sleep")
def sleep(reader: Reader, log: RequestLogDep, start: Start, end: End) -> Sleep:
    """Every sleep, naps included, on the date it ended."""
    checked_range(start, end, MAX_RANGE_DAYS)
    days = SleepAggregator(reader).days(start, end)
    record(log, reader, SLEEP, start, end)
    return Sleep(data_type=SLEEP, days=days)


@router.get("/sleep/temperature")
def sleep_temperature(
    reader: Reader, log: RequestLogDep, start: Start, end: End
) -> Readings:
    return _readings(
        reader,
        log,
        "daily-sleep-temperature-derivations",
        start,
        end,
        {
            "nightly_celsius": "nightlyTemperatureCelsius",
            "baseline_celsius": "baselineTemperatureCelsius",
            "relative_nightly_stddev_30d_celsius": "relativeNightlyStddev30dCelsius",
        },
    )


# --- activity --------------------------------------------------------------


@router.get("/activity/steps")
def steps(
    reader: Reader,
    log: RequestLogDep,
    start: Start,
    end: End,
    resolution: Bucket = Resolution.DAY,
) -> SumSeries:
    checked_range(start, end, MAX_DAYS[resolution])
    buckets = SeriesAggregator(reader).sums(
        ObservationTimeInterval, "steps", start, end, resolution
    )
    record(log, reader, "steps", start, end)
    return SumSeries(
        data_type="steps", unit="steps", resolution=resolution, buckets=buckets
    )


@router.get("/activity/distance")
def distance(
    reader: Reader,
    log: RequestLogDep,
    start: Start,
    end: End,
    resolution: Bucket = Resolution.DAY,
) -> SumSeries:
    checked_range(start, end, MAX_DAYS[resolution])
    buckets = SeriesAggregator(reader).sums(
        ObservationTimeInterval,
        "distance",
        start,
        end,
        resolution,
        divisor=MILLIMETERS_PER_METER,
    )
    record(log, reader, "distance", start, end)
    return SumSeries(
        data_type="distance", unit="m", resolution=resolution, buckets=buckets
    )


@router.get("/activity/zone-minutes")
def active_zone_minutes(
    reader: Reader,
    log: RequestLogDep,
    start: Start,
    end: End,
    resolution: Bucket = Resolution.DAY,
) -> CategorySeries:
    return _categories(
        reader,
        log,
        "active-zone-minutes",
        start,
        end,
        resolution,
        category_key="heartRateZone",
        by_window=False,
    )


@router.get("/activity/floors")
def floors(reader: Reader, log: RequestLogDep, start: Start, end: End) -> Readings:
    return _readings(reader, log, "floors", start, end, {"count": "countSum"})


@router.get("/activity/level")
def activity_level(
    reader: Reader,
    log: RequestLogDep,
    start: Start,
    end: End,
    resolution: Bucket = Resolution.DAY,
) -> CategorySeries:
    return _categories(
        reader,
        log,
        "activity-level",
        start,
        end,
        resolution,
        category_key="activityLevelType",
        by_window=True,
    )


@router.get("/activity/sedentary")
def sedentary(
    reader: Reader, log: RequestLogDep, start: Start, end: End
) -> Sedentary:
    checked_range(start, end, MAX_RANGE_DAYS)
    days = SeriesAggregator(reader).sedentary(
        ObservationTimeInterval, "sedentary-period", start, end
    )
    record(log, reader, "sedentary-period", start, end)
    return Sedentary(data_type="sedentary-period", days=days)


# --- exercise, food and water -----------------------------------------------


@router.get("/exercise")
def exercise(reader: Reader, log: RequestLogDep, start: Start, end: End) -> Exercise:
    checked_range(start, end, MAX_RANGE_DAYS)
    sessions = LogAggregator(reader).exercise(start, end)
    record(log, reader, EXERCISE, start, end)
    return Exercise(data_type=EXERCISE, sessions=sessions)


@router.get("/nutrition")
def nutrition(
    reader: Reader, log: RequestLogDep, start: Start, end: End
) -> Nutrition:
    checked_range(start, end, MAX_RANGE_DAYS)
    days = LogAggregator(reader).nutrition(start, end)
    record(log, reader, NUTRITION_LOG, start, end)
    return Nutrition(data_type=NUTRITION_LOG, days=days)


@router.get("/hydration")
def hydration(
    reader: Reader, log: RequestLogDep, start: Start, end: End
) -> Hydration:
    checked_range(start, end, MAX_RANGE_DAYS)
    days = LogAggregator(reader).hydration(start, end)
    record(log, reader, HYDRATION_LOG, start, end)
    return Hydration(data_type=HYDRATION_LOG, days=days)


# --- body --------------------------------------------------------------------


@router.get("/body/height")
def height(reader: Reader, log: RequestLogDep, start: Start, end: End) -> Readings:
    return _readings(
        reader,
        log,
        "height",
        start,
        end,
        {"meters": "heightMillimeters"},
        table=ObservationSampleTime,
        divisors={"meters": MILLIMETERS_PER_METER},
    )


@router.get("/body/vo2-max")
def vo2_max(reader: Reader, log: RequestLogDep, start: Start, end: End) -> Readings:
    return _readings(
        reader,
        log,
        "vo2-max",
        start,
        end,
        {"ml_per_kg_per_min": "vo2Max"},
        table=ObservationSampleTime,
    )


@router.get("/body/vo2-max/run")
def run_vo2_max(
    reader: Reader, log: RequestLogDep, start: Start, end: End
) -> Readings:
    return _readings(
        reader,
        log,
        "run-vo2-max",
        start,
        end,
        {"ml_per_kg_per_min": "runVo2Max"},
        table=ObservationSampleTime,
    )


# --- shared shapes -----------------------------------------------------------


def _readings(
    reader: MeasurementReader,
    log: RequestLog,
    data_type: str,
    start: dt.date,
    end: dt.date,
    fields: dict[str, str],
    *,
    table: type = UnknownDataPoint,
    divisors: dict[str, float] | None = None,
) -> Readings:
    checked_range(start, end, MAX_RANGE_DAYS)
    readings = SeriesAggregator(reader).readings(
        table, data_type, start, end, fields, divisors
    )
    record(log, reader, data_type, start, end)
    return Readings(data_type=data_type, readings=readings)


def _categories(
    reader: MeasurementReader,
    log: RequestLog,
    data_type: str,
    start: dt.date,
    end: dt.date,
    resolution: Resolution,
    *,
    category_key: str,
    by_window: bool,
) -> CategorySeries:
    """Minutes per category: from window lengths, or from each row's own value."""
    checked_range(start, end, MAX_DAYS[resolution])
    buckets = SeriesAggregator(reader).category_totals(
        ObservationTimeInterval,
        data_type,
        start,
        end,
        resolution,
        category_key,
        minutes_of if by_window else value_of,
    )
    record(log, reader, data_type, start, end)
    return CategorySeries(
        data_type=data_type, unit="minutes", resolution=resolution, buckets=buckets
    )
