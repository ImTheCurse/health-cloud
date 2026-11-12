"""Exercise sessions and the things a user logs by hand: food and water."""

import datetime as dt
from collections import defaultdict
from typing import Any

from server.aggregation.const import (
    EXERCISE_METRICS,
    EXERCISE_ZONE_DURATIONS,
    MILLIMETERS_PER_METER,
)
from server.aggregation.schemas import (
    ExerciseSession,
    HydrationDay,
    Number,
    NutritionDay,
    NutritionEntry,
)
from server.aggregation.series import MeasurementReader
from server.aggregation.util import (
    at_path,
    duration_minutes,
    number,
    tidy,
    tidy_or_none,
    window_minutes,
)
from server.models.datapoint import (
    ObservationTimeInterval,
    SessionTimeInterval,
)

EXERCISE = "exercise"
NUTRITION_LOG = "nutrition-log"
HYDRATION_LOG = "hydration-log"


class LogAggregator:
    """Exercise sessions, food logged per day, and water drunk per day.

    A log's table is not assumed: a food or drink entry carries no sub-intervals,
    so it may be filed as an interval rather than a session, and both are read.
    """

    def __init__(self, reader: MeasurementReader) -> None:
        self._reader = reader

    def exercise(self, start: dt.date, end: dt.date) -> list[ExerciseSession]:
        sessions = []
        for row in self._reader.read(
            SessionTimeInterval, EXERCISE, start, end, with_value=True
        ):
            payload: Any = row.value or {}
            metrics = at_path(payload, "metricsSummary") or {}
            distance = number(metrics.get("distanceMillimeters"))
            sessions.append(
                ExerciseSession(
                    date=row.civil_date,
                    start=row.local_start,
                    end=row.local_end,
                    exercise_type=payload.get("exerciseType"),
                    name=payload.get("displayName"),
                    duration_minutes=tidy(
                        round(window_minutes(row.start_ts, row.end_ts), 2)
                    ),
                    active_minutes=tidy_or_none(
                        duration_minutes(payload.get("activeDuration"))
                    ),
                    distance_meters=None
                    if distance is None
                    else tidy(distance / MILLIMETERS_PER_METER),
                    metrics=_numbers(metrics, EXERCISE_METRICS),
                    zone_minutes=_zone_minutes(metrics.get("heartRateZoneDurations")),
                )
            )
        return sessions

    def nutrition(self, start: dt.date, end: dt.date) -> list[NutritionDay]:
        entries: dict[dt.date, list[NutritionEntry]] = defaultdict(list)
        for row in self._log_rows(NUTRITION_LOG, start, end):
            if row.civil_date is None:
                continue
            payload: Any = row.value or {}
            entries[row.civil_date].append(
                NutritionEntry(
                    time=row.local_start,
                    food=payload.get("foodDisplayName") or payload.get("food"),
                    meal_type=payload.get("mealType"),
                    kcal=tidy_or_none(number(at_path(payload, "energy.kcal"))),
                    grams=_grams(payload),
                )
            )
        days = []
        for day, found in sorted(entries.items()):
            grams: dict[str, float] = defaultdict(float)
            for entry in found:
                for nutrient, amount in entry.grams.items():
                    grams[nutrient] += amount
            days.append(
                NutritionDay(
                    date=day,
                    kcal=tidy(round(sum(float(e.kcal or 0) for e in found), 2)),
                    grams={n: tidy(round(g, 2)) for n, g in sorted(grams.items())},
                    entries=found,
                )
            )
        return days

    def hydration(self, start: dt.date, end: dt.date) -> list[HydrationDay]:
        totals: dict[dt.date, float] = defaultdict(float)
        for row in self._log_rows(HYDRATION_LOG, start, end):
            amount = number(at_path(row.value, "amountConsumed.milliliters"))
            if row.civil_date is not None and amount is not None:
                totals[row.civil_date] += amount
        return [
            HydrationDay(date=day, milliliters=tidy(total))
            for day, total in sorted(totals.items())
        ]

    def _log_rows(self, data_type: str, start: dt.date, end: dt.date) -> list[Any]:
        rows = []
        for table in (SessionTimeInterval, ObservationTimeInterval):
            rows += self._reader.read(table, data_type, start, end, with_value=True)
        rows.sort(key=lambda row: (row.civil_date, row.local_start or dt.datetime.min))
        return rows


def _numbers(payload: Any, fields: dict[str, str]) -> dict[str, Number]:
    found: dict[str, Number] = {}
    for name, field in fields.items():
        value = number(payload.get(field)) if isinstance(payload, dict) else None
        if value is not None:
            found[name] = tidy(value)
    return found


def _zone_minutes(durations: Any) -> dict[str, Number]:
    found: dict[str, Number] = {}
    if not isinstance(durations, dict):
        return found
    for zone, field in EXERCISE_ZONE_DURATIONS.items():
        minutes = duration_minutes(durations.get(field))
        if minutes is not None:
            found[zone] = tidy(round(minutes, 2))
    return found


def _grams(payload: Any) -> dict[str, Number]:
    """Grams of each nutrient in one entry: the totals, then the itemised list."""
    grams: dict[str, Number] = {}
    for name, path in (
        ("carbohydrate", "totalCarbohydrate.grams"),
        ("fat", "totalFat.grams"),
    ):
        value = number(at_path(payload, path))
        if value is not None:
            grams[name] = tidy(value)
    nutrients = payload.get("nutrients") if isinstance(payload, dict) else None
    for item in nutrients if isinstance(nutrients, list) else []:
        if not isinstance(item, dict):
            continue
        nutrient, value = item.get("nutrient"), number(at_path(item, "quantity.grams"))
        if isinstance(nutrient, str) and value is not None:
            grams.setdefault(nutrient.lower(), tidy(value))
    return grams
