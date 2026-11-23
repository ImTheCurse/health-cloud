"""The fetcher flow's request for a rollup run.

A heart-rate message may be acknowledged only once Prefect holds a rollup run
for the hours it wrote: after the ack, nothing else would rebuild them.
"""

import datetime as dt
import logging
import uuid

import pytest

from server.flows import fetch
from server.health.fetcher import FetchResult
from server.rollup.hours import HourSpan
from tests.google_webhook import FAKE_HEALTH_USER_ID

NINE = dt.datetime(2026, 1, 2, 9)


def payload(data_type="heart-rate", notification_id=41):
    return {
        "notification_id": notification_id,
        "pointer": {"dataType": data_type, "healthUserId": FAKE_HEALTH_USER_ID},
    }


def wrote(start=NINE, end=NINE + dt.timedelta(hours=1)):
    return FetchResult("heart-rate", 10, 0, 0, hours=HourSpan(start, end))


@pytest.fixture
def requested(monkeypatch):
    """Every run the flow asked Prefect for, without a Prefect server."""
    calls = []

    class Run:
        id = uuid.UUID(int=7)

    async def fake_run_deployment(name, **kwargs):
        calls.append({"name": name, **kwargs})
        return Run()

    monkeypatch.setattr(fetch, "arun_deployment", fake_run_deployment)
    return calls


async def test_the_run_covers_the_hours_written(requested):
    run_id = await fetch.request_rollup(payload(), [wrote()])

    assert run_id == str(uuid.UUID(int=7))
    [call] = requested
    assert call["name"] == "rollup-heart-rate/rollup"
    assert call["parameters"] == {
        "health_user_id": FAKE_HEALTH_USER_ID,
        "start": "2026-01-02T09:00:00",
        "end": "2026-01-02T10:00:00",
    }


async def test_the_flow_does_not_wait_for_the_run_to_finish(requested):
    await fetch.request_rollup(payload(), [wrote()])

    assert requested[0]["timeout"] == 0


async def test_several_intervals_make_one_run_over_all_their_hours(requested):
    later = NINE + dt.timedelta(hours=5)

    await fetch.request_rollup(
        payload(), [wrote(later, later + dt.timedelta(hours=1)), wrote()]
    )

    [call] = requested
    assert (call["parameters"]["start"], call["parameters"]["end"]) == (
        "2026-01-02T09:00:00",
        "2026-01-02T15:00:00",
    )


async def test_nothing_rolled_up_asks_for_no_run(requested):
    steps = FetchResult("steps", 10, 0, 0)

    assert await fetch.request_rollup(payload("steps"), [steps]) is None
    assert requested == []


async def test_a_redelivery_reuses_the_key_a_new_notification_does_not(requested):
    """Prefect returns the existing run for a key it has seen, so a redelivered
    message cannot start a second run -- but a later notification about the same
    hours must, or its correction would never be rolled up."""
    await fetch.request_rollup(payload(notification_id=41), [wrote()])
    await fetch.request_rollup(payload(notification_id=41), [wrote()])
    await fetch.request_rollup(payload(notification_id=42), [wrote()])

    keys = [call["idempotency_key"] for call in requested]
    assert keys[0] == keys[1]
    assert keys[2] != keys[0]


async def test_a_run_that_cannot_be_created_fails_the_message(monkeypatch):
    """The consumer acks only when the task returns, so raising is what keeps
    the message for redelivery."""

    async def unreachable(name, **kwargs):
        raise ConnectionError("prefect is down")

    monkeypatch.setattr(fetch, "arun_deployment", unreachable)
    monkeypatch.setattr(fetch, "_fetch_blocking", lambda payload: [wrote()])
    # Outside a Prefect run there is no run logger to have.
    monkeypatch.setattr(fetch, "get_run_logger", lambda: logging.getLogger("test"))

    with pytest.raises(ConnectionError):
        await fetch.fetch_pointer.fn(payload())
