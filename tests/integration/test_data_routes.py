"""The read routes over real, encrypted rows.

The unit tests prove the arithmetic over rows from memory. This proves the rows
the routes see are the ones the database really holds: decrypted, narrowed to the
signed-in user and to the chosen sources, and dated as the routes say.
"""

import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from server.api.auth import current_user
from server.db.upsert import upsert_data_point, upsert_many
from server.main import app
from server.models.datapoint import ObservationTimeInterval, SessionTimeInterval
from server.models.user import User
from tests.api.conftest import SESSION_DEPENDENCY

USER = "1234567890123456789"
OTHER_USER = "9876543210987654321"
NOW = dt.datetime(2026, 10, 31, 12, tzinfo=dt.UTC)
DAY = dt.date(2026, 10, 30)


def steps(record_id, hour, count, *, platform="FITBIT", user=USER):
    start = dt.datetime.combine(DAY, dt.time(hour), tzinfo=dt.UTC)
    return ObservationTimeInterval(
        health_user_id=user,
        data_type="steps",
        record_id=record_id,
        source_platform=platform,
        start_ts=start,
        end_ts=start + dt.timedelta(minutes=5),
        local_start=start.replace(tzinfo=None),
        local_end=(start + dt.timedelta(minutes=5)).replace(tzinfo=None),
        civil_date=DAY,
        value_numeric=Decimal(count),
        value_unit="count",
        value={"count": str(count)},
        raw={"steps": {"count": str(count)}},
        fetched_at=NOW,
    )


@pytest.fixture
def client(session):
    app.dependency_overrides[current_user] = lambda: User(
        health_user_id=USER,
        google_sub="sub",
        email="user@example.com",
        refresh_token_enc=b"x",
        granted_scopes="",
        consented_at=NOW,
        refreshed_at=NOW,
    )
    app.dependency_overrides[SESSION_DEPENDENCY] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_steps_are_decrypted_summed_and_kept_to_one_user_and_source(client, session):
    upsert_many(
        session,
        [
            steps("a", 9, 400),
            steps("b", 10, 12),
            steps("phone", 9, 999, platform="HEALTH_KIT"),
            steps("someone-else", 9, 5000, user=OTHER_USER),
        ],
    )
    session.commit()

    response = client.get(
        "/data/activity/steps", params={"start": "2026-10-30", "end": "2026-10-31"}
    )

    assert response.status_code == 200
    assert response.json()["buckets"] == [{"start": "2026-10-30T00:00:00", "total": 412}]


def test_a_night_is_read_back_on_its_wake_up_date(client, session):
    start = dt.datetime(2026, 10, 29, 23, tzinfo=dt.UTC)
    end = dt.datetime(2026, 10, 30, 7, tzinfo=dt.UTC)
    upsert_data_point(
        session,
        SessionTimeInterval(
            health_user_id=USER,
            data_type="sleep",
            record_id="night",
            source_platform="FITBIT",
            start_ts=start,
            end_ts=end,
            local_start=start.replace(tzinfo=None),
            local_end=end.replace(tzinfo=None),
            civil_date=start.date(),
            value={"summary": {"minutesAsleep": "430"}, "metadata": {"mainSleep": True}},
            raw={"sleep": {}},
            fetched_at=NOW,
        ),
    )
    session.commit()

    response = client.get(
        "/data/sleep", params={"start": "2026-10-30", "end": "2026-10-31"}
    )

    [day] = response.json()["days"]
    assert day["date"] == "2026-10-30"
    assert day["total_minutes_asleep"] == 430
