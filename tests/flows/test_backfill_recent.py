"""The scheduled backfill flow, without a Prefect server or Google.

Each type's task is replaced, so these cover the flow's own decisions: the
window, the order, what a failure stops, and the rollup run it asks for.
"""

import datetime as dt
import logging

import pytest

from server.flows import backfill
from server.flows.error import BackfillFailed
from server.health.backfill import backfill_types
from server.health.error import TokenExpiredError
from server.health.fetcher import FetchResult
from server.rollup.hours import HourSpan
from tests.google_webhook import FAKE_HEALTH_USER_ID

NINE = dt.datetime(2026, 11, 25, 9)


@pytest.fixture
def flow(monkeypatch):
    """The flow with every type succeeding, and a record of what it did."""
    record: dict = {"calls": [], "rollups": [], "failing": {}}

    async def fake_backfill_one_type(health_user_id, data_type, start, end):
        record["calls"].append((data_type, start, end))
        error = record["failing"].get(data_type)
        if error is not None:
            raise error
        hours = (
            HourSpan(NINE, NINE + dt.timedelta(hours=2))
            if data_type == "heart-rate"
            else None
        )
        return FetchResult(data_type, 1, 0, 0, hours=hours)

    async def fake_request_rollup(health_user_id, hours):
        record["rollups"].append((health_user_id, hours))
        return "rollup-run"

    monkeypatch.setattr(backfill, "backfill_one_type", fake_backfill_one_type)
    monkeypatch.setattr(backfill, "request_rollup", fake_request_rollup)
    monkeypatch.setattr(backfill, "_user_ids", lambda: [FAKE_HEALTH_USER_ID])
    monkeypatch.setattr(
        backfill, "get_run_logger", lambda: logging.getLogger("test")
    )
    return record


async def test_every_type_is_fetched_in_order_over_the_last_day(flow):
    await backfill.backfill_recent.fn()

    assert [call[0] for call in flow["calls"]] == list(backfill_types())
    _, start, end = flow["calls"][0]
    assert end - start == dt.timedelta(days=1)


async def test_a_manual_run_can_reach_further_back(flow):
    await backfill.backfill_recent.fn(window_hours=72)

    _, start, end = flow["calls"][0]
    assert end - start == dt.timedelta(hours=72)


async def test_a_failed_type_does_not_stop_the_others(flow):
    flow["failing"]["exercise"] = RuntimeError("Google said no")

    with pytest.raises(BackfillFailed, match="exercise"):
        await backfill.backfill_recent.fn()

    assert [call[0] for call in flow["calls"]] == list(backfill_types())


async def test_an_expired_token_stops_the_run(flow):
    """Every other type would fail the same way."""
    first = backfill_types()[0]
    flow["failing"][first] = TokenExpiredError("dead")

    with pytest.raises(TokenExpiredError):
        await backfill.backfill_recent.fn()

    assert [call[0] for call in flow["calls"]] == [first]


async def test_heart_rate_hours_get_a_rollup_run(flow):
    await backfill.backfill_recent.fn()

    assert flow["rollups"] == [
        (FAKE_HEALTH_USER_ID, HourSpan(NINE, NINE + dt.timedelta(hours=2)))
    ]


async def test_no_rollup_run_without_heart_rate_hours(flow, monkeypatch):
    monkeypatch.setattr(backfill, "backfill_types", lambda: ("steps", "exercise"))

    await backfill.backfill_recent.fn()

    assert flow["rollups"] == []
