"""The scheduled backfill flow.

Every hour, Prefect's scheduler starts a ``backfill-recent`` run that fetches the
last day of every type for every consented user. Webhooks are the fast path and
this is the safety net: Google lists a workout only once it is finished, sends
no notification for the finished session, and loses notifications sent to an
endpoint that is down. A fetch over a window that has since been filled stores
what those notifications would have.

It uses the same per-type strategy as ``backfill run`` (``server.health.backfill``)
and, like the fetcher, starts a ``rollup-heart-rate`` run for the heart-rate
hours it wrote.

**A failed type does not stop the others.** Each type is its own task, so the
Prefect UI shows which one failed, and the run is marked failed at the end if
any did. An expired token is the exception: every other type would fail the
same way, so the run stops at once.
"""

import datetime as dt

import anyio.to_thread
from prefect import flow, get_run_logger, task
from prefect.deployments import arun_deployment
from prefect.runtime import flow_run
from sqlmodel import select

from server.db.session import get_session
from server.flows.error import BackfillFailed
from server.health.backfill import backfill_type, backfill_types
from server.health.error import TokenExpiredError
from server.health.fetcher import FetchResult
from server.models.user import User
from server.observability.util import hashed_log_id
from server.orchestration.const import BACKFILL_WINDOW, ROLLUP_DEPLOYMENT
from server.providers import build_fetcher, build_user_repository
from server.rollup.hours import HourSpan


@task
async def backfill_one_type(
    health_user_id: str, data_type: str, start: dt.datetime, end: dt.datetime
) -> FetchResult:
    """Fetch and store one type over ``[start, end)`` for one user.

    No Prefect retries: the next scheduled run covers the same window less an
    hour, so a type that failed is fetched again within the hour.
    """
    logger = get_run_logger()

    def run() -> FetchResult:
        with get_session() as session:
            user = build_user_repository(session).get(health_user_id)
            if user is None:
                return FetchResult(data_type, 0, 0, 0)
            return backfill_type(build_fetcher(session), user, data_type, start, end)

    result = await anyio.to_thread.run_sync(run)
    logger.info("backfilled %s (user %s)", result, hashed_log_id(health_user_id))
    return result


@flow(name="backfill-recent", log_prints=True)
async def backfill_recent(window_hours: int | None = None) -> str:
    """Fetch the last ``window_hours`` of every type for every consented user.

    The types run **one after another, never in parallel**, because of Google's
    rate limit of 300 requests a minute per user. One run makes roughly 30 to 60
    requests, and a single unfiltered type such as heart-rate pages through
    thousands of points; run side by side, the types could reach the limit and
    turn a backfill into a string of 429s.

    Args:
        window_hours: how far back to reach. The schedule leaves it unset, for
            ``BACKFILL_WINDOW``; a manual run can ask for more.
    """
    logger = get_run_logger()
    window = (
        dt.timedelta(hours=window_hours) if window_hours is not None else BACKFILL_WINDOW
    )
    end = dt.datetime.now(dt.UTC)
    start = end - window

    failed: list[str] = []
    for health_user_id in await anyio.to_thread.run_sync(_user_ids):
        user = hashed_log_id(health_user_id)
        hours: HourSpan | None = None
        for data_type in backfill_types():
            try:
                result = await backfill_one_type(health_user_id, data_type, start, end)
            except TokenExpiredError:
                logger.error(
                    "backfill stopped for user %s: the refresh token is dead; "
                    "re-consent is needed",
                    user,
                )
                raise
            except Exception as error:
                # A database error's message can include bound health data. Log
                # its type, never its message.
                logger.error(
                    "backfill failed for %s (user %s): %s",
                    data_type,
                    user,
                    type(error).__name__,
                )
                failed.append(data_type)
                continue
            if result.hours is not None:
                hours = result.hours.union(hours)

        if hours is not None:
            run_id = await request_rollup(health_user_id, hours)
            logger.info("requested rollup run %s (user %s)", run_id, user)

    if failed:
        raise BackfillFailed(f"could not backfill: {', '.join(failed)}")
    return f"backfilled {start.isoformat()} to {end.isoformat()}"


async def request_rollup(health_user_id: str, hours: HourSpan) -> str:
    """Create a rollup run for the hours the backfill wrote.

    The idempotency key names this flow run, so a retried run gets back the
    rollup run it already created.
    """
    key = ":".join(
        [
            "backfill",
            str(flow_run.get_id()),
            health_user_id,
            hours.start.isoformat(),
            hours.end.isoformat(),
        ]
    )
    run = await arun_deployment(
        ROLLUP_DEPLOYMENT,
        parameters={
            "health_user_id": health_user_id,
            "start": hours.start.isoformat(),
            "end": hours.end.isoformat(),
        },
        timeout=0,
        idempotency_key=key,
        as_subflow=False,
    )
    return str(run.id)


def _user_ids() -> list[str]:
    """Every consented user. One today, by design, but nothing here assumes it."""
    with get_session() as session:
        return list(session.exec(select(User.health_user_id)))
