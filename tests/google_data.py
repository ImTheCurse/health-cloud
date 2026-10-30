"""Sample ``DataPoint`` payloads.

Two kinds live here, and the difference matters.

``live_*`` fixtures follow **shapes verified against the real API on 2026-09-28**,
with every value invented. The documentation turned out to be wrong in three ways
that a test could not have caught on its own: a real point carries **no ``name``**
(only ``dataSource`` and the measurement), ``civilStartTime`` is a **nested**
object rather than an ISO string, and ``dataSource`` holds
``recordingMethod``/``device``/``platform`` rather than a stream name.

The others follow the API reference. They are kept because the reference describes
them and the parser accepts both, but they are not evidence of anything: this is
the same documentation that described the webhook payload as a bare object when it
is an array of envelopes.

Every value is invented, the way ``tests/google_webhook.py`` invents its own, so
no real measurement, device name or time reaches the repository.
"""

from typing import Any

from tests.google_webhook import FAKE_HEALTH_USER_ID, FAKE_RECORD_ID

USER_PATH = f"users/{FAKE_HEALTH_USER_ID}/dataTypes"


def interval_point(
    data_type: str = "steps",
    record_id: str = FAKE_RECORD_ID,
    count: str = "4210",
    payload_key: str | None = None,
) -> dict[str, Any]:
    """``ObservationTimeInterval``: accumulated over a window.

    The civil fields carry no offset, and the physical ones do -- that pairing is
    what the local columns are derived from.
    """
    key = payload_key or data_type
    return {
        "name": f"{USER_PATH}/{data_type}/dataPoints/{record_id}",
        "dataSource": {"streamName": "derived:com.google.step_count"},
        key: {
            "interval": {
                "startTime": "2026-01-02T09:00:00Z",
                "endTime": "2026-01-02T10:00:00Z",
                "startUtcOffset": "-14400s",
                "endUtcOffset": "-14400s",
            },
            "count": count,
        },
    }


def sample_point(
    data_type: str = "weight",
    record_id: str = FAKE_RECORD_ID,
    value: float = 81.4,
    unit: str = "kg",
) -> dict[str, Any]:
    """``ObservationSampleTime``: measured at an instant."""
    return {
        "name": f"{USER_PATH}/{data_type}/dataPoints/{record_id}",
        "dataSource": {"streamName": "raw:com.google.weight"},
        data_type: {
            "sampleTime": {
                "physicalTime": "2026-01-02T07:30:00Z",
                "utcOffset": "-14400s",
            },
            "mass": {"value": value, "unit": unit},
        },
    }


def heart_rate_point(record_id: str = FAKE_RECORD_ID, bpm: int = 72) -> dict[str, Any]:
    """A sample whose measurement is a bare number, not a quantity object."""
    return {
        "name": f"{USER_PATH}/heart_rate/dataPoints/{record_id}",
        "heart_rate": {
            "sampleTime": {
                "physicalTime": "2026-01-02T07:30:00Z",
                "utcOffset": "-14400s",
            },
            "beatsPerMinute": bpm,
        },
    }


def session_point(
    record_id: str = FAKE_RECORD_ID, with_stages: bool = True
) -> dict[str, Any]:
    """``SessionTimeInterval``: a window bundling metrics and sub-intervals."""
    sleep: dict[str, Any] = {
        "interval": {
            "startTime": "2026-01-01T22:00:00Z",
            "endTime": "2026-01-02T06:00:00Z",
            "startUtcOffset": "-14400s",
            "endUtcOffset": "-14400s",
        },
        "type": "STAGES",
        "minutesToFallAsleep": 12,
        "minutesAfterWakeup": 5,
    }
    if with_stages:
        sleep["stages"] = [
            {
                "startTime": "2026-01-01T22:00:00Z",
                "endTime": "2026-01-01T23:30:00Z",
                "startUtcOffset": "-14400s",
                "endUtcOffset": "-14400s",
                "type": "LIGHT",
            },
            {
                "startTime": "2026-01-01T23:30:00Z",
                "endTime": "2026-01-02T01:00:00Z",
                "startUtcOffset": "-14400s",
                "endUtcOffset": "-14400s",
                "type": "DEEP",
            },
        ]
        sleep["shortAwakenings"] = [
            {
                "startTime": "2026-01-02T01:00:00Z",
                "endTime": "2026-01-02T01:05:00Z",
                "type": "AWAKE",
            }
        ]
    return {
        "name": f"{USER_PATH}/sleep/dataPoints/{record_id}",
        "sleep": sleep,
    }


def all_day_point(data_type: str = "active_minutes") -> dict[str, Any]:
    """A full-day activity, which omits the physical interval entirely.

    The reason ``start_ts`` is nullable: for these, the civil time is the only
    time there is.
    """
    return {
        "name": f"{USER_PATH}/{data_type}/dataPoints/{FAKE_RECORD_ID}",
        data_type: {
            "interval": {
                "civilStartTime": "2026-01-02T00:00:00",
                "civilEndTime": "2026-01-03T00:00:00",
            },
            "minutes": 45,
        },
    }


def unrecognisable_point(data_type: str = "brand_new_type") -> dict[str, Any]:
    """A type Google added after this code was written, with no time we know."""
    return {
        "name": f"{USER_PATH}/{data_type}/dataPoints/{FAKE_RECORD_ID}",
        data_type: {"somethingNew": {"weCannotParse": True}},
    }


def live_interval_point(
    data_type: str = "steps", count: str = "412", start_hour: int = 9
) -> dict[str, Any]:
    """The shape a real ``steps`` point arrives in.

    No ``name``: this is why the record id is derived from the window and source
    rather than read off the payload. The civil times are nested under ``date``
    and ``time``, which the flat-object parser silently failed to read.
    """
    return {
        "dataSource": {
            "recordingMethod": "RECORDING_METHOD_AUTOMATICALLY_RECORDED",
            "device": {"displayName": "Invented Watch"},
            "platform": "PLATFORM_ANDROID",
        },
        data_type: {
            "interval": {
                "startTime": f"2026-01-02T{start_hour:02d}:00:00Z",
                "startUtcOffset": "-14400s",
                "endTime": f"2026-01-02T{start_hour + 1:02d}:00:00Z",
                "endUtcOffset": "-14400s",
                "civilStartTime": {
                    "date": {"year": 2026, "month": 1, "day": 2},
                    "time": {"hours": start_hour - 4, "minutes": 0},
                },
                "civilEndTime": {
                    "date": {"year": 2026, "month": 1, "day": 2},
                    "time": {"hours": start_hour - 3, "minutes": 0},
                },
            },
            "count": count,
        },
    }


def live_daily_summary_point(data_type: str = "daily-resting-heart-rate") -> dict[str, Any]:
    """A daily summary: a **fourth** time shape, carrying a bare ``date``.

    Found on the first real run, when this type landed in ``unknown_data_points``.
    It is neither an interval nor a sample, so it stays in the catch-all until a
    table is worth building for it -- but its date is read, so the row is still
    queryable by day rather than opaque.
    """
    return {
        "dataSource": {"platform": "PLATFORM_ANDROID"},
        "dailyRestingHeartRate": {
            "beatsPerMinute": 58,
            "date": {"year": 2026, "month": 1, "day": 2},
            "dailyRestingHeartRateMetadata": {},
        },
    }
