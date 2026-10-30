"""Two requests in flight must never see each other's record.

The record is per-request state on a shared server, so this is the property
that matters most: it is the one whose failure would be intermittent, look
like corrupted data rather than a crash, and be miserable to track down.

Each request here sleeps while holding its record, so they are genuinely
overlapping rather than running one after another.
"""

import asyncio

import httpx2
import pytest
from fastapi import FastAPI

from server.observability.context import RequestLogDep
from server.observability.middleware import log_requests
from server.observability.util import hashed_log_id

CALLERS = 25


@pytest.fixture
def anyio_backend():
    return "asyncio"


def build_app() -> FastAPI:
    app = FastAPI()
    app.middleware("http")(log_requests)

    @app.get("/work/{caller}")
    async def work(log: RequestLogDep, caller: str) -> dict:
        log.set_user(caller)
        # Hold the record open across a suspension point, so every caller is
        # inside this handler at the same time.
        await asyncio.sleep(0.02)
        log.add_event("worked", caller=caller)
        return {"caller": caller}

    return app


@pytest.mark.anyio
async def test_concurrent_requests_keep_their_own_records(logs):
    transport = httpx2.ASGITransport(app=build_app())
    async with httpx2.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        await asyncio.gather(*(client.get(f"/work/caller-{i}") for i in range(CALLERS)))

    assert len(logs) == CALLERS, "one record per request, no more and no fewer"

    for entry in logs:
        extra = entry.record["extra"]
        assert len(extra["events"]) == 1, (
            f"expected exactly one event, got {extra['events']} -- another "
            "request wrote into this record"
        )
        # The user was set before the sleep and the event after it. If state
        # leaked between requests these would belong to different callers.
        caller = extra["events"][0]["caller"]
        assert extra["user"] == hashed_log_id(caller), (
            f"{extra['user']} is not {caller}"
        )
        assert extra["path"] == f"/work/{caller}"

    ids = {entry.record["extra"]["request_id"] for entry in logs}
    assert len(ids) == CALLERS, "request ids collided"

    callers = {entry.record["extra"]["events"][0]["caller"] for entry in logs}
    assert callers == {f"caller-{i}" for i in range(CALLERS)}
