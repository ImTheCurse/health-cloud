"""The read routes: who may call them, which ranges they accept, what they return."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from server.aggregation.const import MAX_DAYS, MAX_RANGE_DAYS, Resolution
from server.api.data import get_reader
from server.main import app
from tests.aggregation.fakes import reader_over, row
from tests.conftest import logged_text

ROUTES = [
    path
    for path in app.openapi()["paths"]
    if path.startswith("/data")
]
DAY = dt.date(2026, 10, 30)


@pytest.fixture
def serve():
    """A signed-in client whose reads come from the rows a test supplies."""

    def client_over(**rows):
        reader = reader_over(**rows)
        app.dependency_overrides[get_reader] = lambda: reader
        return TestClient(app)

    yield client_over
    app.dependency_overrides.clear()


def test_there_is_a_route_for_every_stored_kind_of_data():
    assert len(ROUTES) == 24


@pytest.mark.parametrize("path", ROUTES)
def test_every_route_needs_a_session(client, path):
    response = client.get(path, params={"start": "2026-10-01", "end": "2026-10-02"})

    assert response.status_code == 401


@pytest.mark.parametrize("path", ROUTES)
def test_every_route_answers_with_no_data(serve, path):
    response = serve().get(path, params={"start": "2026-10-01", "end": "2026-10-02"})

    assert response.status_code == 200


@pytest.mark.parametrize(
    "params",
    [
        {"start": "2026-10-02", "end": "2026-10-02"},
        {"start": "2026-10-03", "end": "2026-10-02"},
        {"start": "2026-10-01"},
        {"start": "not-a-date", "end": "2026-10-02"},
        {"start": "2026-10-01", "end": "2026-10-02", "resolution": "2m"},
    ],
)
def test_a_bad_range_is_refused(serve, params):
    assert serve().get("/data/heart-rate", params=params).status_code == 422


@pytest.mark.parametrize("resolution", list(Resolution))
def test_each_resolution_has_its_own_range_cap(serve, resolution):
    start = dt.date(2026, 1, 1)
    within = start + dt.timedelta(days=MAX_DAYS[resolution])
    client = serve()

    def status(end):
        return client.get(
            "/data/activity/steps",
            params={"start": start, "end": end, "resolution": resolution},
        ).status_code

    assert status(within) == 200
    assert status(within + dt.timedelta(days=1)) == 422


def test_a_week_of_daily_data_is_one_request(serve):
    response = serve().get(
        "/data/heart-rate", params={"start": "2026-10-24", "end": "2026-10-31"}
    )

    assert response.status_code == 200


def test_a_route_without_resolution_caps_at_a_year(serve):
    start = dt.date(2026, 1, 1)
    end = start + dt.timedelta(days=MAX_RANGE_DAYS + 1)

    response = serve().get("/data/sleep", params={"start": start, "end": end})

    assert response.status_code == 422


def test_steps_come_back_as_a_typed_series(serve):
    client = serve(
        steps=[
            row(dt.datetime(2026, 10, 30, 9, 1), numeric=400),
            row(dt.datetime(2026, 10, 30, 9, 20), numeric=12),
        ]
    )

    response = client.get(
        "/data/activity/steps",
        params={"start": "2026-10-30", "end": "2026-10-31", "resolution": "1h"},
    )

    assert response.json() == {
        "data_type": "steps",
        "unit": "steps",
        "resolution": "1h",
        "buckets": [{"start": "2026-10-30T09:00:00", "total": 412}],
    }


def test_a_read_is_logged_without_its_values(serve, logs):
    client = serve(heart_rate=[row(dt.datetime(2026, 10, 30, 9), numeric=987654)])

    client.get("/data/heart-rate", params={"start": "2026-10-30", "end": "2026-10-31"})

    assert logs, "nothing was logged, so the check below would pass vacuously"
    rendered = logged_text(logs)
    assert "measurements_read" in rendered
    assert "987654" not in rendered
