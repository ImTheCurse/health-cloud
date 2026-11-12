"""Response models for the read API.

Times are the user's local clock, with no timezone: a chart of "my Tuesday" is
drawn on the clock the user was living by, which is also how the dashboard
groups days. Numbers are plain ints and floats; a Decimal would serialise as a
string.
"""

import datetime as dt

from pydantic import BaseModel

from server.aggregation.const import Resolution

Number = int | float


class StatBucket(BaseModel):
    """Samples in one bucket: their lowest, mean and highest value."""

    start: dt.datetime
    min: Number
    avg: Number
    max: Number
    count: int


class StatSeries(BaseModel):
    data_type: str
    unit: str
    resolution: Resolution
    buckets: list[StatBucket]


class SumBucket(BaseModel):
    start: dt.datetime
    total: Number


class SumSeries(BaseModel):
    data_type: str
    unit: str
    resolution: Resolution
    buckets: list[SumBucket]


class CategoryBucket(BaseModel):
    """A total per category in one bucket: minutes per zone, per level."""

    start: dt.datetime
    totals: dict[str, Number]


class CategorySeries(BaseModel):
    data_type: str
    unit: str
    resolution: Resolution
    buckets: list[CategoryBucket]


class Reading(BaseModel):
    """One stored value set: a daily summary, a nightly summary, a sample.

    ``time`` is null for a daily summary, which Google dates but does not time.
    """

    date: dt.date
    time: dt.datetime | None
    values: dict[str, Number]


class Readings(BaseModel):
    data_type: str
    readings: list[Reading]


class ZoneLimit(BaseModel):
    zone: str
    min_bpm: Number | None
    max_bpm: Number | None


class ZoneLimitsDay(BaseModel):
    date: dt.date
    zones: list[ZoneLimit]


class ZoneLimits(BaseModel):
    data_type: str
    days: list[ZoneLimitsDay]


class Period(BaseModel):
    start: dt.datetime | None
    end: dt.datetime | None
    minutes: Number


class SedentaryDay(BaseModel):
    date: dt.date
    minutes: Number
    periods: list[Period]


class Sedentary(BaseModel):
    data_type: str
    days: list[SedentaryDay]


class SleepStage(BaseModel):
    stage: str
    start: dt.datetime | None
    end: dt.datetime | None
    minutes: Number


class SleepSession(BaseModel):
    """One sleep, main or nap. The summary minutes are Google's own."""

    start: dt.datetime | None
    end: dt.datetime | None
    duration_minutes: Number
    main_sleep: bool
    minutes_asleep: Number | None
    minutes_awake: Number | None
    minutes_in_sleep_period: Number | None
    minutes_to_fall_asleep: Number | None
    minutes_after_wakeup: Number | None
    stage_minutes: dict[str, Number]
    stages: list[SleepStage]
    short_awakenings: list[SleepStage]


class SleepDay(BaseModel):
    """Every sleep that ended on ``date``, naps included."""

    date: dt.date
    total_minutes_asleep: Number
    sessions: list[SleepSession]


class Sleep(BaseModel):
    data_type: str
    days: list[SleepDay]


class ExerciseSession(BaseModel):
    date: dt.date | None
    start: dt.datetime | None
    end: dt.datetime | None
    exercise_type: str | None
    name: str | None
    duration_minutes: Number
    active_minutes: Number | None
    distance_meters: Number | None
    metrics: dict[str, Number]
    zone_minutes: dict[str, Number]


class Exercise(BaseModel):
    data_type: str
    sessions: list[ExerciseSession]


class NutritionEntry(BaseModel):
    time: dt.datetime | None
    food: str | None
    meal_type: str | None
    kcal: Number | None
    grams: dict[str, Number]


class NutritionDay(BaseModel):
    date: dt.date
    kcal: Number
    grams: dict[str, Number]
    entries: list[NutritionEntry]


class Nutrition(BaseModel):
    data_type: str
    days: list[NutritionDay]


class HydrationDay(BaseModel):
    date: dt.date
    milliliters: Number


class Hydration(BaseModel):
    data_type: str
    days: list[HydrationDay]
