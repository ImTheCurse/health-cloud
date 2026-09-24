"""Which level each request is reported at.

Not sampling: nothing is discarded and nothing is decided by chance. The
policy only chooses a level, so a request logged at DEBUG is still there for
anyone who lowers the threshold to look.

Locally everything is worth seeing. Elsewhere a route that opted into QUIET
drops routine successes to DEBUG but still speaks up when something happened.
"""

from dataclasses import dataclass

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from server.observability import middleware
from server.observability.const import QUIET
from server.observability.context import RequestLog
from server.observability.policy import log_policy
from tests.observability.test_request_log import build_app


@dataclass
class FakeSettings:
    environment: str


@pytest.fixture
def deployed(monkeypatch):
    """Pretend we are not on the developer's laptop."""
    monkeypatch.setattr(
        middleware, "get_settings", lambda: FakeSettings(environment="production")
    )
    return TestClient(build_app(), raise_server_exceptions=False)


def level_of(logs):
    assert len(logs) == 1
    return logs[0].record["level"].name


def test_locally_even_a_quiet_route_is_logged(logs):
    """ENVIRONMENT=local in .env, so this is the default fixture's world."""
    TestClient(build_app()).get("/quiet")

    assert level_of(logs) == "INFO"


def test_a_quiet_route_drops_routine_success_to_debug(deployed, logs):
    deployed.get("/quiet")

    assert level_of(logs) == "DEBUG"


def test_a_quiet_route_speaks_up_on_an_error_status(deployed, logs):
    """404s are the reason you went looking at the log in the first place."""
    deployed.get("/quiet-but-broken")

    assert level_of(logs) == "INFO"


def test_a_route_that_said_nothing_is_still_logged_in_full(deployed, logs):
    """The default is ALWAYS: a route is only quietened if it asked to be."""
    deployed.get("/plain")

    assert level_of(logs) == "INFO"


def test_a_quiet_route_speaks_up_when_it_has_events(deployed, logs):
    """An event means something happened worth keeping, whatever the status."""

    @log_policy(QUIET)
    def endpoint() -> None: ...

    record = RequestLog(
        request_id="x",
        method="GET",
        path="/quiet",
        is_secure=False,
        x_forwarded_for=None,
        status=200,
    )
    request = Request({"type": "http", "endpoint": endpoint, "headers": []})

    assert middleware._level(record, request) == "DEBUG"

    record.events.append({"event": "notification"})
    assert middleware._level(record, request) == "INFO"
