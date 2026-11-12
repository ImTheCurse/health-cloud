"""Constants for turning stored measurements into chart series."""

from enum import StrEnum
from typing import Final

from server.models.const import FITBIT_PLATFORM, GOOGLE_HEALTH_PLATFORM


class Resolution(StrEnum):
    """How wide each bucket of a time series is, on the user's local clock."""

    MINUTE = "1m"
    FIVE_MINUTES = "5m"
    TEN_MINUTES = "10m"
    HALF_HOUR = "30m"
    HOUR = "1h"
    DAY = "1d"


#: The width of each resolution in minutes.
RESOLUTION_MINUTES: Final[dict[Resolution, int]] = {
    Resolution.MINUTE: 1,
    Resolution.FIVE_MINUTES: 5,
    Resolution.TEN_MINUTES: 10,
    Resolution.HALF_HOUR: 30,
    Resolution.HOUR: 60,
    Resolution.DAY: 24 * 60,
}

#: The longest range, in days, one request may ask for at each resolution. Keeps
#: a response to a few thousand buckets: two days of minutes is 2,880.
MAX_DAYS: Final[dict[Resolution, int]] = {
    Resolution.MINUTE: 2,
    Resolution.FIVE_MINUTES: 7,
    Resolution.TEN_MINUTES: 14,
    Resolution.HALF_HOUR: 31,
    Resolution.HOUR: 92,
    Resolution.DAY: 366,
}

#: The longest range for a route with no resolution: one entry per day or less.
MAX_RANGE_DAYS: Final = 366

#: Sources a read keeps. Steps, distance and exercise arrive from more than one
#: platform with overlapping windows, so summing every source counts the same
#: activity twice. ``GOOGLE_HEALTH`` is a total Google already deduplicated.
READ_PLATFORMS: Final[tuple[str, ...]] = (FITBIT_PLATFORM, GOOGLE_HEALTH_PLATFORM)

#: Decimal places kept on an average. Enough to draw, not enough to imply a
#: precision the sensor does not have.
AVERAGE_PLACES: Final = 1

#: Millimetres in a metre. Google states distance and height in millimetres.
MILLIMETERS_PER_METER: Final = 1000

#: Sleep summary fields, as Google names them, and the names the API returns.
SLEEP_SUMMARY_FIELDS: Final[dict[str, str]] = {
    "minutes_asleep": "minutesAsleep",
    "minutes_awake": "minutesAwake",
    "minutes_in_sleep_period": "minutesInSleepPeriod",
    "minutes_to_fall_asleep": "minutesToFallAsleep",
    "minutes_after_wakeup": "minutesAfterWakeUp",
}

#: Exercise ``metricsSummary`` fields that are plain numbers, and the names the
#: API returns.
EXERCISE_METRICS: Final[dict[str, str]] = {
    "average_heart_rate_bpm": "averageHeartRateBeatsPerMinute",
    "calories_kcal": "caloriesKcal",
    "steps": "steps",
    "active_zone_minutes": "activeZoneMinutes",
    "average_pace_seconds_per_meter": "averagePaceSecondsPerMeter",
}

#: Exercise heart-rate zone durations, keyed by the zone name the API returns.
EXERCISE_ZONE_DURATIONS: Final[dict[str, str]] = {
    "LIGHT": "lightTime",
    "MODERATE": "moderateTime",
    "VIGOROUS": "vigorousTime",
    "PEAK": "peakTime",
}
