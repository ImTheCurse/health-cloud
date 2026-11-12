"""Sleep by wake-up day, exercise sessions, and food and water logs."""

import datetime as dt

from server.aggregation.logs import LogAggregator
from server.aggregation.sleep import SleepAggregator
from server.models.datapoint import ObservationTimeInterval, SessionTimeInterval
from tests.aggregation.fakes import reader_over, row

TUE = dt.date(2026, 10, 27)
WED = TUE + dt.timedelta(days=1)
THU = WED + dt.timedelta(days=1)


def at(day, hour, minute=0):
    return dt.datetime.combine(day, dt.time(hour, minute))


def stage(kind, start, end):
    """A nested stage window as Google sends it: UTC plus an offset of zero."""
    return {
        "type": kind,
        "startTime": start.isoformat() + "Z",
        "endTime": end.isoformat() + "Z",
        "startUtcOffset": "0s",
        "endUtcOffset": "0s",
    }


def night(start, end, asleep, *, main=True):
    return row(
        start,
        local_end=end,
        value={
            "metadata": {"mainSleep": main},
            "summary": {
                "minutesAsleep": str(asleep),
                "minutesAwake": "30",
                "minutesToFallAsleep": "12",
                "minutesAfterWakeUp": "4",
                "minutesInSleepPeriod": "400",
                "stagesSummary": [
                    {"type": "DEEP", "minutes": "60", "count": "3"},
                    {"type": "LIGHT", "minutes": "250", "count": "20"},
                ],
            },
            "stages": [
                stage("LIGHT", at(start.date(), 23, 30), at(start.date(), 23, 45)),
                stage("DEEP", start, at(start.date(), 23, 30)),
            ],
            "shortAwakenings": [
                stage("LIGHT", at(start.date(), 23, 40), at(start.date(), 23, 42))
            ],
        },
    )


def test_a_night_belongs_to_the_day_it_ended():
    """Stored on Tuesday, because it started then; read as Wednesday's."""
    reader = reader_over(sleep=[night(at(TUE, 23), at(WED, 7), 420)])

    [day] = SleepAggregator(reader).days(WED, THU)

    assert day.date == WED
    assert day.total_minutes_asleep == 420


def test_a_night_ending_outside_the_range_is_left_out():
    reader = reader_over(sleep=[night(at(TUE, 23), at(WED, 7), 420)])

    assert SleepAggregator(reader).days(TUE, WED) == []


def test_naps_add_to_the_days_total():
    reader = reader_over(
        sleep=[
            night(at(TUE, 23), at(WED, 7), 420),
            night(at(WED, 15), at(WED, 15, 40), 35, main=False),
        ]
    )

    [day] = SleepAggregator(reader).days(WED, THU)

    assert day.total_minutes_asleep == 455
    assert [s.main_sleep for s in day.sessions] == [True, False]


def test_a_session_carries_googles_summary_and_its_stages():
    reader = reader_over(sleep=[night(at(TUE, 23), at(WED, 7), 420)])

    [day] = SleepAggregator(reader).days(WED, THU)
    [session] = day.sessions

    assert session.duration_minutes == 480
    assert session.minutes_asleep == 420
    assert session.minutes_to_fall_asleep == 12
    assert session.minutes_in_sleep_period == 400
    assert session.stage_minutes == {"DEEP": 60, "LIGHT": 250}
    assert [(s.stage, s.start, s.minutes) for s in session.stages] == [
        ("DEEP", at(TUE, 23), 30),
        ("LIGHT", at(TUE, 23, 30), 15),
    ]
    assert [(s.start, s.minutes) for s in session.short_awakenings] == [
        (at(TUE, 23, 40), 2)
    ]


def test_an_exercise_session_reads_its_summary():
    reader = reader_over(
        exercise=[
            row(
                at(TUE, 18),
                minutes=45,
                value={
                    "exerciseType": "RUNNING",
                    "displayName": "Run",
                    "activeDuration": "2400s",
                    "metricsSummary": {
                        "distanceMillimeters": 5200000,
                        "steps": "6100",
                        "averageHeartRateBeatsPerMinute": "151",
                        "heartRateZoneDurations": {"peakTime": "300s", "lightTime": "60s"},
                    },
                },
            )
        ]
    )

    [session] = LogAggregator(reader).exercise(TUE, WED)

    assert session.exercise_type == "RUNNING"
    assert session.duration_minutes == 45
    assert session.active_minutes == 40
    assert session.distance_meters == 5200
    assert session.metrics == {"average_heart_rate_bpm": 151, "steps": 6100}
    assert session.zone_minutes == {"LIGHT": 1, "PEAK": 5}


def meal(hour, kcal, carbs, protein):
    return row(
        at(TUE, hour),
        value={
            "foodDisplayName": "Invented food",
            "mealType": "LUNCH",
            "energy": {"kcal": kcal},
            "totalCarbohydrate": {"grams": carbs},
            "nutrients": [{"nutrient": "PROTEIN", "quantity": {"grams": protein}}],
        },
    )


def test_nutrition_totals_each_day_and_keeps_the_entries():
    reader = reader_over(
        tables={"nutrition-log": SessionTimeInterval},
        nutrition_log=[meal(12, 500.5, 40, 20), meal(19, 300, 10, 15)],
    )

    [day] = LogAggregator(reader).nutrition(TUE, WED)

    assert day.kcal == 800.5
    assert day.grams == {"carbohydrate": 50, "protein": 35}
    assert [e.time for e in day.entries] == [at(TUE, 12), at(TUE, 19)]


def test_hydration_is_millilitres_per_day():
    reader = reader_over(
        tables={"hydration-log": ObservationTimeInterval},
        hydration_log=[
            row(at(TUE, 9), value={"amountConsumed": {"milliliters": 250}}),
            row(at(TUE, 15), value={"amountConsumed": {"milliliters": 500}}),
        ]
    )

    [day] = LogAggregator(reader).hydration(TUE, WED)

    assert (day.date, day.milliliters) == (TUE, 750)
