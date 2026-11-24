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


# --- the backfill's rollup run, which does carry its input ---


def test_a_run_can_carry_parameters():
    transport = FakeTransport()

    trigger_with(transport).trigger({"health_user_id": "u", "start": "s"})

    assert transport.requests[0]["json"] == {
        "parameters": {"health_user_id": "u", "start": "s"}
    }


def test_a_deployment_is_found_by_name():
    transport = FakeTransport([FakeResponse(200, {"id": DEPLOYMENT})])

    trigger = FlowTrigger.by_name(
        "http://prefect:4200/api",
        "rollup-heart-rate/rollup",
        session=transport,  # type: ignore[arg-type]
    )
    trigger.trigger()

    lookup, created = transport.requests
    assert lookup["url"] == (
        "http://prefect:4200/api/deployments/name/rollup-heart-rate/rollup"
    )
    assert created["url"].endswith(f"/deployments/{DEPLOYMENT}/create_flow_run")


def test_a_deployment_prefect_does_not_know_raises():
    transport = FakeTransport([FakeResponse(404)])

    with pytest.raises(TriggerError, match="404"):
        FlowTrigger.by_name(
            "http://prefect:4200/api",
            "rollup-heart-rate/rollup",
            session=transport,  # type: ignore[arg-type]
        )


# --- the receiver's doorbell, which finds the fetcher by name ---


def named_trigger_with(transport):
    return FlowTrigger(
        "http://prefect:4200/api",
        session=transport,  # type: ignore[arg-type]
        deployment_name="fetch-notifications/fetcher",
    )


def test_a_named_trigger_makes_no_call_until_it_is_rung():
    """It is built while the app starts, when Prefect may not be up yet."""
    transport = FakeTransport()

    named_trigger_with(transport)

    assert transport.requests == []


def test_a_named_trigger_looks_the_name_up_once():
    transport = FakeTransport([FakeResponse(200, {"id": DEPLOYMENT})])
    trigger = named_trigger_with(transport)

    trigger.trigger()
    trigger.trigger()

    urls = [request["url"] for request in transport.requests]
    assert urls == [
        "http://prefect:4200/api/deployments/name/fetch-notifications/fetcher",
        f"http://prefect:4200/api/deployments/{DEPLOYMENT}/create_flow_run",
        f"http://prefect:4200/api/deployments/{DEPLOYMENT}/create_flow_run",
    ]


def test_a_failed_lookup_is_tried_again_on_the_next_ring():
    """Prefect not being up yet must not leave the doorbell broken for good."""
    transport = FakeTransport(
        [FakeResponse(404), FakeResponse(200, {"id": DEPLOYMENT})]
    )
    trigger = named_trigger_with(transport)

    with pytest.raises(TriggerError, match="404"):
        trigger.trigger()
    trigger.trigger()

    assert transport.requests[-1]["url"].endswith(
        f"/deployments/{DEPLOYMENT}/create_flow_run"
    )


def test_a_deployment_prefect_has_forgotten_is_looked_up_again():
    """Deleting and re-registering a deployment gives it a new id."""
    transport = FakeTransport(
        [
            FakeResponse(200, {"id": DEPLOYMENT}),  # the lookup
            FakeResponse(201, {"id": "run-1"}),  # the first run
            FakeResponse(404),  # the id is gone
            FakeResponse(200, {"id": "new-id"}),  # the second lookup
        ]
    )
    trigger = named_trigger_with(transport)
    trigger.trigger()

    with pytest.raises(TriggerError, match="404"):
        trigger.trigger()
    trigger.trigger()

    assert transport.requests[-1]["url"].endswith("/deployments/new-id/create_flow_run")


def test_a_trigger_needs_exactly_one_of_an_id_and_a_name():
    with pytest.raises(ValueError):
        FlowTrigger("http://prefect:4200/api")
    with pytest.raises(ValueError):
        FlowTrigger(
            "http://prefect:4200/api", DEPLOYMENT, deployment_name="flow/deployment"
        )
