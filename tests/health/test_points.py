"""Deciding what a payload is, and turning it into a row.

The routing design lives or dies here: a data type Google adds tomorrow must land
somewhere sensible rather than crashing, and a type we do know must land in the
right table with its times intact.
"""

import datetime as dt
from decimal import Decimal

import pytest

from server.health.points import build, classify, measurement_of, record_id_of
from server.models.const import SegmentType, TimeStructure
from server.models.datapoint import (
    ObservationSampleTime,
    ObservationTimeInterval,
    SessionTimeInterval,
    UnknownDataPoint,
)
from tests.google_data import (
    all_day_point,
    heart_rate_point,
    interval_point,
    live_daily_summary_point,
    live_interval_point,
    sample_point,
    session_point,
    unrecognisable_point,
)
from tests.google_webhook import FAKE_HEALTH_USER_ID

FETCHED = dt.datetime(2026, 1, 3, 12, 0, tzinfo=dt.UTC)


def row_for(point, data_type):
    return build(
        point,
        health_user_id=FAKE_HEALTH_USER_ID,
        data_type=data_type,
        fetched_at=FETCHED,
    )


# --- finding the measurement ---


def test_the_measurement_is_found_by_elimination():
    """By name would need a list of 29 types; by elimination needs nothing."""
    key, payload = measurement_of(interval_point("steps"))

    assert key == "steps"
    assert "count" in payload


def test_an_unheard_of_type_still_yields_its_payload():
    key, payload = measurement_of(unrecognisable_point("brand_new_type"))

    assert key == "brand_new_type"
    assert payload == {"somethingNew": {"weCannotParse": True}}


# --- classification ---


def test_an_interval_payload_is_an_interval():
    _, payload = measurement_of(interval_point("steps"))

    assert classify("steps", payload) is TimeStructure.INTERVAL


def test_a_sample_payload_is_a_sample():
    _, payload = measurement_of(sample_point("weight"))

    assert classify("weight", payload) is TimeStructure.SAMPLE


def test_a_sample_is_identified_without_the_seed_table():
    """``sampleTime`` is unambiguous, so an unseeded type is still classified."""
    _, payload = measurement_of(sample_point("brand_new_vital"))

    assert classify("brand_new_vital", payload) is TimeStructure.SAMPLE


def test_a_session_is_identified_by_its_segments():
    """Sessions and intervals are field-identical; sub-intervals give it away."""
    _, payload = measurement_of(session_point())

    assert classify("totally_unseeded", payload) is TimeStructure.SESSION


def test_a_segmentless_session_falls_back_to_the_seed_table():
    """The one case the payload cannot decide, so the seed has to."""
    _, payload = measurement_of(session_point(with_stages=False))

    assert classify("sleep", payload) is TimeStructure.SESSION
    assert classify("unseeded", payload) is TimeStructure.INTERVAL


def test_an_unrecognisable_shape_is_unknown_not_an_error():
    """Google adding a type must be a row, not an exception on a live fetch."""
    _, payload = measurement_of(unrecognisable_point())

    assert classify("brand_new_type", payload) is TimeStructure.UNKNOWN


# --- which table ---


@pytest.mark.parametrize(
    "point, data_type, table",
    [
        (interval_point("steps"), "steps", ObservationTimeInterval),
        (sample_point("weight"), "weight", ObservationSampleTime),
        (heart_rate_point(), "heart_rate", ObservationSampleTime),
        (session_point(), "sleep", SessionTimeInterval),
        (unrecognisable_point(), "brand_new_type", UnknownDataPoint),
    ],
)
def test_each_shape_goes_to_its_own_table(point, data_type, table):
    row, _ = row_for(point, data_type)

    assert isinstance(row, table)


# --- times ---


def test_an_interval_keeps_utc_and_local_side_by_side():
    row, _ = row_for(interval_point("steps"), "steps")

    assert row.start_ts == dt.datetime(2026, 1, 2, 9, 0, tzinfo=dt.UTC)
    assert row.end_ts == dt.datetime(2026, 1, 2, 10, 0, tzinfo=dt.UTC)
    # 09:00Z at -4h is 05:00 on the user's clock, with no zone attached.
    assert row.local_start == dt.datetime(2026, 1, 2, 5, 0)
    assert row.local_start.tzinfo is None


def test_the_civil_date_is_the_local_day_not_the_utc_one():
    """ "My Tuesday" means Tuesday where the user was standing.

    A 23:00Z reading at -5h happened on the previous local day, and a dashboard
    grouping on the UTC date would file it under the wrong one.
    """
    point = interval_point("steps")
    point["steps"]["interval"]["startTime"] = "2026-01-02T23:00:00Z"
    point["steps"]["interval"]["startUtcOffset"] = "-18000s"

    row, _ = row_for(point, "steps")

    assert row.start_ts.date() == dt.date(2026, 1, 2)
    assert row.civil_date == dt.date(2026, 1, 2)
    assert row.local_start == dt.datetime(2026, 1, 2, 18, 0)


def test_a_sample_puts_the_instant_at_both_ends():
    """So "between two times" is one query shape across all three tables."""
    row, _ = row_for(sample_point("weight"), "weight")

    assert row.start_ts == row.end_ts == dt.datetime(2026, 1, 2, 7, 30, tzinfo=dt.UTC)


def test_a_full_day_activity_has_no_physical_interval():
    """Which is why the UTC columns are nullable and the civil ones carry it."""
    row, _ = row_for(all_day_point(), "active_minutes")

    assert row.start_ts is None
    assert row.local_start == dt.datetime(2026, 1, 2, 0, 0)
    assert row.civil_date == dt.date(2026, 1, 2)


# --- values ---


def test_an_int64_in_a_string_becomes_a_number():
    row, _ = row_for(interval_point("steps", count="4210"), "steps")

    assert row.value_numeric == Decimal(4210)
    assert row.value_unit == "count"


def test_a_quantity_object_keeps_its_unit():
    row, _ = row_for(sample_point("weight", value=81.4, unit="kg"), "weight")

    assert row.value_numeric == Decimal("81.4")
    assert row.value_unit == "kg"


def test_a_bare_number_takes_its_field_name_as_the_unit():
    row, _ = row_for(heart_rate_point(bpm=72), "heart_rate")

    assert row.value_numeric == Decimal(72)
    assert row.value_unit == "beatsPerMinute"


def test_a_composite_payload_has_no_single_number():
    """A sleep session is not a number, and inventing one would be a lie."""
    row, _ = row_for(session_point(), "sleep")

    assert row.value_numeric is None
    assert row.value["type"] == "STAGES"


# --- raw, and identity ---


def test_the_whole_datapoint_is_kept():
    """The column that makes a modelling mistake fixable from our own database."""
    point = interval_point("steps")

    row, _ = row_for(point, "steps")

    assert row.raw == point


def test_even_an_unrecognisable_point_keeps_its_payload():
    point = unrecognisable_point()

    row, _ = row_for(point, "brand_new_type")

    assert row.raw == point
    assert row.value == {"somethingNew": {"weCannotParse": True}}


def test_the_record_id_is_the_tail_of_the_resource_name():
    assert record_id_of(interval_point(record_id="abc123")) == "abc123"


def test_a_real_point_has_no_name_so_the_id_is_derived():
    """Verified against the live API: a real point carries no identifier at all.

    The reference describes a ``name``; the API does not send one. So the id comes
    from the window and the source instead.
    """
    point = live_interval_point()

    assert "name" not in point
    assert record_id_of(point).startswith("d-")


def test_a_derived_id_survives_a_correction_to_the_value():
    """The property the whole upsert design rests on. Keying on the value would
    make a correction look like a new record and insert a second row beside the one
    it was meant to replace."""
    original = live_interval_point(count="412")
    corrected = live_interval_point(count="999")

    assert record_id_of(original) == record_id_of(corrected)


def test_a_different_window_is_a_different_record():
    assert record_id_of(live_interval_point(start_hour=9)) != record_id_of(
        live_interval_point(start_hour=11)
    )


def test_a_point_with_nothing_to_identify_it_is_refused():
    """Without an identity every point of a type would collapse onto one row, so
    this fails loudly rather than writing a row keyed on nothing."""
    with pytest.raises(ValueError, match="neither a name nor"):
        record_id_of({"steps": {}})


def test_the_real_nested_civil_time_is_read():
    """The flat-object parser returned None for every real payload, and the local
    columns silently fell back to deriving from the offset -- same answer by luck,
    and no error either way."""
    row, _ = row_for(live_interval_point(start_hour=9), "steps")

    assert row.local_start == dt.datetime(2026, 1, 2, 5, 0)
    assert row.civil_date == dt.date(2026, 1, 2)


def test_a_real_point_still_routes_and_values_correctly():
    row, _ = row_for(live_interval_point(count="412"), "steps")

    assert isinstance(row, ObservationTimeInterval)
    assert row.value_numeric == Decimal(412)
    assert row.start_ts == dt.datetime(2026, 1, 2, 9, 0, tzinfo=dt.UTC)


# --- segments ---


def test_a_session_yields_its_stages():
    _, segments = row_for(session_point(), "sleep")

    assert [s.label for s in segments] == ["LIGHT", "DEEP", "AWAKE"]


def test_short_awakenings_are_stages_too():
    """Google puts them in a separate array; both are sleep stages."""
    _, segments = row_for(session_point(), "sleep")

    assert all(s.segment_type == SegmentType.SLEEP_STAGE for s in segments)


def test_a_segment_carries_its_own_window():
    _, segments = row_for(session_point(), "sleep")

    first = segments[0]
    assert first.start_ts == dt.datetime(2026, 1, 1, 22, 0, tzinfo=dt.UTC)
    assert first.end_ts == dt.datetime(2026, 1, 1, 23, 30, tzinfo=dt.UTC)
    assert first.local_start == dt.datetime(2026, 1, 1, 18, 0)


def test_only_sessions_produce_segments():
    _, segments = row_for(interval_point("steps"), "steps")

    assert segments == []


def test_a_deleted_pointer_tombstones_rather_than_removing():
    row, _ = build(
        interval_point("steps"),
        health_user_id=FAKE_HEALTH_USER_ID,
        data_type="steps",
        fetched_at=FETCHED,
        deleted_at=FETCHED,
    )

    assert row.deleted_at == FETCHED


# --- the fourth shape ---


def test_a_daily_summary_lands_in_the_catch_all():
    """Neither an interval nor a sample. Found on the first real run rather than
    designed for, which is the catch-all earning its place: the payload was kept
    with no schema guessed for it."""
    row, _ = row_for(live_daily_summary_point(), "daily-resting-heart-rate")

    assert isinstance(row, UnknownDataPoint)


def test_a_daily_summary_still_gets_a_date():
    """Without this the row is safe but opaque -- no start_ts, no civil_date, so
    nothing can ask "what was my resting heart rate on Tuesday"."""
    row, _ = row_for(live_daily_summary_point(), "daily-resting-heart-rate")

    assert row.civil_date == dt.date(2026, 1, 2)
    assert row.start_ts is None


def test_a_daily_summary_keeps_its_number():
    row, _ = row_for(live_daily_summary_point(), "daily-resting-heart-rate")

    assert row.value_numeric == Decimal(58)
    assert row.value_unit == "beatsPerMinute"


def test_daily_summaries_on_different_dates_have_different_ids():
    earlier = live_daily_summary_point()
    later = live_daily_summary_point()
    later["dailyRestingHeartRate"]["date"]["day"] = 3

    earlier_row, _ = row_for(earlier, "daily-resting-heart-rate")
    later_row, _ = row_for(later, "daily-resting-heart-rate")

    assert earlier_row.record_id != later_row.record_id


def test_correcting_a_daily_value_keeps_the_same_id():
    earlier = live_daily_summary_point()
    corrected = live_daily_summary_point()
    corrected["dailyRestingHeartRate"]["beatsPerMinute"] = 61

    earlier_row, _ = row_for(earlier, "daily-resting-heart-rate")
    corrected_row, _ = row_for(corrected, "daily-resting-heart-rate")

    assert earlier_row.record_id == corrected_row.record_id
