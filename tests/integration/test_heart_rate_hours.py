"""Rebuilding and reading the hourly heart-rate summaries, against real Postgres.

What a fake cannot show: that the rebuild's ``WHERE`` clauses pick exactly the
rows of the span, that it replaces rather than adds to what was there, and that
the summaries come back decrypted and filtered by source.
"""

import datetime as dt
from decimal import Decimal

from sqlalchemy import func, select

from server.db.upsert import upsert_many
from server.models.datapoint import ObservationSampleTime, ObservationTimeInterval
from server.models.rollup import HeartRateHour
from server.rollup.hours import HeartRateHours, HourSpan

USER = "1234567890123456789"
OTHER_USER = "9876543210987654321"
NOW = dt.datetime(2026, 9, 28, 12, 0, tzinfo=dt.UTC)
DAY = dt.date(2026, 9, 27)
SPAN = HourSpan(dt.datetime(2026, 9, 27), dt.datetime(2026, 9, 28))
FITBIT = ("FITBIT",)


def sample(record_id, local, bpm, *, user=USER, platform="FITBIT", **extra):
    return ObservationSampleTime(
        health_user_id=user,
        data_type="heart-rate",
        record_id=record_id,
        source_platform=platform,
        start_ts=local.replace(tzinfo=dt.UTC),
        local_start=local,
        civil_date=local.date(),
        value_numeric=Decimal(bpm),
        value_unit="bpm",
        value={"beatsPerMinute": bpm},
        raw={"heartRate": {"beatsPerMinute": bpm}},
        fetched_at=NOW,
        **extra,
    )


def in_zone(record_id, local, minutes, zone):
    end = local + dt.timedelta(minutes=minutes)
    return ObservationTimeInterval(
        health_user_id=USER,
        data_type="time-in-heart-rate-zone",
        record_id=record_id,
        source_platform="FITBIT",
        start_ts=local.replace(tzinfo=dt.UTC),
        end_ts=end.replace(tzinfo=dt.UTC),
        local_start=local,
        local_end=end,
        civil_date=local.date(),
        value={"heartRateZoneType": zone},
        raw={"timeInHeartRateZone": {"heartRateZoneType": zone}},
        fetched_at=NOW,
    )


def at(hour, minute=0):
    return dt.datetime.combine(DAY, dt.time(hour, minute))


def summaries(session, platforms=FITBIT, start=DAY, end=DAY + dt.timedelta(days=1)):
    return {
        hour.hour_start: hour.summary
        for hour in HeartRateHours(session).read(USER, start, end, platforms)
    }


def test_an_hour_holds_its_samples_figures_and_zone_minutes(session):
    upsert_many(
        session,
        [
            sample("a", at(9, 1), 60),
            sample("b", at(9, 59), 90),
            in_zone("z1", at(9, 10), 12, "FAT_BURN"),
            in_zone("z2", at(9, 30), 3, "CARDIO"),
        ],
    )

    written = HeartRateHours(session).rebuild(USER, SPAN)

    assert written == 1
    assert summaries(session) == {
        at(9): {
            "count": 2,
            "sum": 150.0,
            "min": 60.0,
            "max": 90.0,
            "zone_minutes": {"CARDIO": 3.0, "FAT_BURN": 12.0},
        }
    }


def test_rebuilding_twice_leaves_the_same_rows(session):
    upsert_many(session, [sample("a", at(9), 60), sample("b", at(10), 70)])
    hours = HeartRateHours(session)

    hours.rebuild(USER, SPAN)
    first = summaries(session)
    hours.rebuild(USER, SPAN)

    assert summaries(session) == first
    assert session.execute(select(func.count()).select_from(HeartRateHour)).scalar() == 2


def test_a_tombstoned_sample_drops_out_on_rebuild(session):
    upsert_many(session, [sample("a", at(9), 60), sample("b", at(9, 5), 200)])
    HeartRateHours(session).rebuild(USER, SPAN)

    upsert_many(session, [sample("b", at(9, 5), 200, deleted_at=NOW)])
    HeartRateHours(session).rebuild(USER, SPAN)

    assert summaries(session)[at(9)]["max"] == 60.0


def test_an_hour_left_with_nothing_is_removed(session):
    upsert_many(session, [sample("a", at(9), 60)])
    HeartRateHours(session).rebuild(USER, SPAN)

    upsert_many(session, [sample("a", at(9), 60, deleted_at=NOW)])
    HeartRateHours(session).rebuild(USER, SPAN)

    assert summaries(session) == {}


def test_a_rebuild_touches_only_its_own_hours_and_user(session):
    upsert_many(
        session,
        [
            sample("a", at(8), 60),
            sample("b", at(9), 70),
            sample("c", at(9), 80, user=OTHER_USER),
        ],
    )
    hours = HeartRateHours(session)
    hours.rebuild(USER, SPAN)

    upsert_many(session, [sample("a", at(8), 65), sample("b", at(9), 75)])
    hours.rebuild(USER, HourSpan(at(9), at(10)))

    found = summaries(session)
    assert found[at(8)]["sum"] == 60.0, "outside the span, so not rebuilt"
    assert found[at(9)]["sum"] == 75.0
    other = hours.read(OTHER_USER, DAY, DAY + dt.timedelta(days=1), FITBIT)
    assert other == [], "the other user's samples were never rebuilt"


def test_each_source_gets_its_own_row_and_reads_filter_by_source(session):
    upsert_many(
        session,
        [sample("a", at(9), 60), sample("b", at(9), 100, platform="HEALTH_KIT")],
    )

    assert HeartRateHours(session).rebuild(USER, SPAN) == 2

    assert summaries(session)[at(9)]["count"] == 1
    assert summaries(session, ("FITBIT", "HEALTH_KIT"))  # both rows readable


def test_a_rebuild_in_chunks_commits_each_day(session):
    upsert_many(
        session,
        [sample("a", at(9), 60), sample("b", at(9) + dt.timedelta(days=1), 70)],
    )
    chunks = []

    written = HeartRateHours(session).rebuild_in_chunks(
        USER,
        HourSpan(dt.datetime.combine(DAY, dt.time()), at(0) + dt.timedelta(days=2)),
        on_chunk=lambda chunk, count: chunks.append((chunk.start.date(), count)),
    )

    assert written == 2
    assert chunks == [(DAY, 1), (DAY + dt.timedelta(days=1), 1)]
