"""Ringing Prefect's doorbell.

Everything about this client is shaped by one fact: the notification is already
durably queued before it is called. So it must carry no data, and its failure
must be nothing more than a delay.
"""

import pytest

from server.orchestration.client import FlowTrigger
from server.orchestration.error import TriggerError
from tests.health.fakes import ExplodingTransport, FakeResponse, FakeTransport

DEPLOYMENT = "4f2c8a1e-0000-0000-0000-000000000000"


def trigger_with(transport):
    return FlowTrigger(
        api_url="http://prefect:4200/api",
        deployment_id=DEPLOYMENT,
        session=transport,  # type: ignore[arg-type]
    )


def test_it_posts_to_the_deployments_create_run_endpoint():
    transport = FakeTransport()

    trigger_with(transport).trigger()

    assert transport.requests[0]["url"] == (
        f"http://prefect:4200/api/deployments/{DEPLOYMENT}/create_flow_run"
    )


def test_the_trigger_carries_no_payload():
    """The flow's input is the queue. Sending the pointers here would mean either
    the stream is never drained or every pointer is handled twice -- and it would
    put the work back into a fire-and-forget HTTP call, which has no persistence
    or acknowledgement of its own."""
    transport = FakeTransport()

    trigger_with(transport).trigger()

    assert transport.requests[0]["json"] == {}


def test_the_run_id_is_returned_when_given():
    transport = FakeTransport([FakeResponse(201, {"id": "run-42"})])

    assert trigger_with(transport).trigger() == "run-42"


def test_no_run_id_is_not_a_failure():
    """Prefect accepted it, which is all the trigger needs; the id is only useful
    for correlating a log line with a run in the UI."""
    transport = FakeTransport([FakeResponse(200, {})])

    assert trigger_with(transport).trigger() is None


def test_an_answer_that_is_not_json_is_not_a_failure():
    transport = FakeTransport([FakeResponse(200, None)])

    assert trigger_with(transport).trigger() is None


def test_an_error_status_raises():
    transport = FakeTransport([FakeResponse(422)])

    with pytest.raises(TriggerError, match="422"):
        trigger_with(transport).trigger()


def test_an_unreachable_prefect_raises():
    with pytest.raises(TriggerError, match="could not reach"):
        trigger_with(ExplodingTransport()).trigger()


def test_a_trailing_slash_on_the_api_url_does_not_double_up():
    transport = FakeTransport()

    FlowTrigger(
        api_url="http://prefect:4200/api/",
        deployment_id=DEPLOYMENT,
        session=transport,  # type: ignore[arg-type]
    ).trigger()

    assert "//deployments" not in transport.requests[0]["url"]
