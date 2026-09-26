"""The aggregated request record.

One line per request carrying the whole story, rather than a line per thing
that happened -- so these check what that single record contains, including
when the request blew up.
"""

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from server.observability.const import QUIET
from server.observability.context import add_event, set_user_to_request
from server.observability.middleware import log_requests
from server.observability.policy import log_policy
from server.observability.util import hashed_log_id
from tests.google_webhook import FAKE_HEALTH_USER_ID


def build_app() -> FastAPI:
    app = FastAPI()
    app.middleware("http")(log_requests)

    @app.get("/plain")
    def plain() -> dict:
        return {"ok": True}

    @app.get("/eventful")
    def eventful(request: Request) -> dict:
        set_user_to_request(request, FAKE_HEALTH_USER_ID)
        add_event(request, "notification", data_type="sleep")
        return {"ok": True}

    @app.get("/boom")
    def boom() -> dict:
        raise RuntimeError("something gave way")

    @app.get("/quiet")
    @log_policy(QUIET)
    def quiet() -> dict:
        return {"ok": True}

    @app.get("/quiet-but-broken")
    @log_policy(QUIET)
    def quiet_but_broken() -> dict:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="gone")

    return app


@pytest.fixture
def app_client():
    return TestClient(build_app(), raise_server_exceptions=False)


def only_record(logs):
    assert len(logs) == 1, f"expected one aggregated record, got {len(logs)}"
    return logs[0].record["extra"]


def test_one_request_produces_exactly_one_record(app_client, logs):
    app_client.get("/plain")

    assert len(logs) == 1


def test_the_record_carries_the_request_shape(app_client, logs):
    app_client.get("/plain")
    extra = only_record(logs)

    assert extra["method"] == "GET"
    assert extra["path"] == "/plain"
    assert extra["status"] == 200
    assert extra["duration_ms"] >= 0
    assert extra["request_id"]


def test_events_added_in_a_handler_reach_the_record(app_client, logs):
    """The handler and the middleware hold the same object, via request.state."""
    app_client.get("/eventful")
    extra = only_record(logs)

    assert extra["events"] == [{"event": "notification", "data_type": "sleep"}]


def test_the_user_is_hashed_never_raw(app_client, logs):
    app_client.get("/eventful")
    extra = only_record(logs)

    assert extra["user"] == hashed_log_id(FAKE_HEALTH_USER_ID)
    assert FAKE_HEALTH_USER_ID not in str(extra)


def test_the_request_id_is_echoed_to_the_caller(app_client, logs):
    response = app_client.get("/plain")

    assert response.headers["x-request-id"] == only_record(logs)["request_id"]


def test_each_request_gets_its_own_id(app_client, logs):
    app_client.get("/plain")
    app_client.get("/plain")

    assert (
        logs[0].record["extra"]["request_id"] != logs[1].record["extra"]["request_id"]
    )


def test_an_inbound_request_id_is_ignored(app_client, logs):
    """Trusting the caller's id would let anyone forge or collide correlation."""
    app_client.get("/plain", headers={"X-Request-ID": "attacker-chosen"})

    assert only_record(logs)["request_id"] != "attacker-chosen"


def test_a_crash_still_emits_a_record(app_client, logs):
    """The whole point of the finally: the requests worth seeing are the ones
    that failed."""
    app_client.get("/boom")
    extra = only_record(logs)

    assert extra["error"]["cause"] == "RuntimeError"
    assert extra["error"]["message"] == "something gave way"
    assert logs[0].record["level"].name == "ERROR"


def test_the_forwarded_client_is_recorded(app_client, logs):
    """Behind a tunnel this is the only clue who actually called."""
    app_client.get("/plain", headers={"X-Forwarded-For": "74.125.212.136"})

    assert only_record(logs)["x_forwarded_for"] == "74.125.212.136"


def test_the_forwarded_protocol_decides_is_secure(app_client, logs):
    """The hop to the app is plain HTTP behind ngrok or cloudflared."""
    app_client.get("/plain", headers={"X-Forwarded-Proto": "https"})

    assert only_record(logs)["is_secure"] is True
