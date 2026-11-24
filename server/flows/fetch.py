"""The fetcher flow.

Drains the notification queue: for every change pointer the receiver published,
refresh the user's token if needed, ask the Health API what the values are, upsert
them, and only then acknowledge the message.

Two properties are worth stating because everything else follows from them.

**The queue is the input, not the trigger.** A run takes no parameters. The
receiver's trigger is a doorbell that carries no data, so a lost trigger costs
latency and a duplicated one costs nothing -- a work-queue stream hands each
message to exactly one consumer, so overlapping runs cannot double-process.

**The ack comes last.** A message is acknowledged only after its upsert has
committed, which is what makes at-least-once mean something. If anything fails,
the message is left alone and the broker redelivers it.

**A heart-rate message also needs its rollup run to exist.** Before a
heart-rate or time-in-zone message is acknowledged, a ``rollup-heart-rate`` run
for the hours it wrote must have been created in Prefect. The ack does not wait
for that run to finish; Prefect retries it. If the run cannot be created, the
message is redelivered and the whole unit, upsert included, repeats harmlessly.

The flow is ``async`` because ``nats-py`` is, and it uses FastAPI's and Prefect's
loop rather than opening one. The blocking half -- SQLModel and ``requests`` --
goes to a worker thread as one unit per pointer, the same shape the webhook route
uses for its audit write.
"""

import asyncio
from typing import Any

import anyio.to_thread
from loguru import logger as thread_logger
from prefect import flow, get_run_logger, serve, task
from prefect.deployments import arun_deployment

from server.config.settings import get_settings
from server.db.session import get_session
from server.flows.rollup import rollup_heart_rate
from server.health.error import TokenExpiredError
from server.health.fetcher import FetchResult
from server.observability.util import hashed_log_id
from server.orchestration.const import (
    FETCHER_DEPLOYMENT_NAME,
    ROLLUP_DEPLOYMENT,
    ROLLUP_DEPLOYMENT_NAME,
)
from server.providers import build_fetcher, build_user_repository
from server.queue.consumer import NotificationConsumer
from server.queue.error import DrainAborted


@task
async def fetch_pointer(payload: dict[str, Any]) -> str:
    """Fetch everything one change pointer describes.

    Raises whatever the fetch raised, so the consumer leaves the message
    unacknowledged. Returning normally is what earns the ack.

    **No Prefect-level retries, deliberately.** JetStream's redelivery already is
    the retry, and it is the better one: it survives the process dying, where an
    in-process retry does not. A second layer would also need to exclude an
    expired token, and ``retry_condition_fn`` hands the state's result back as a
    coroutine, so such a check silently never runs and the one error that must
    not be retried is retried.
    """
    logger = get_run_logger()
    pointer = payload.get("pointer")
    pointer = pointer if isinstance(pointer, dict) else {}
    data_type = pointer.get("dataType") or "unknown"
    operation = pointer.get("operation")
    operation = operation if operation in ("UPSERT", "DELETE") else "unknown"
    intervals = pointer.get("intervals")
    interval_count = len(intervals) if isinstance(intervals, list) else 0
    health_user_id = pointer.get("healthUserId")
    user = (
        hashed_log_id(health_user_id) if isinstance(health_user_id, str) else "unknown"
    )
    logger.info(
        "fetching %s: %s, %d interval(s), user %s",
        data_type,
        operation,
        interval_count,
        user,
    )

    try:
        results = await anyio.to_thread.run_sync(lambda: _fetch_blocking(payload))
    except TokenExpiredError as error:
        logger.error(
            "fetch failed for %s (user %s): TokenExpiredError", data_type, user
        )
        # Nothing else in the queue can succeed either, so stop rather than spend
        # every remaining message's redelivery budget discovering that.
        raise DrainAborted(
            "the refresh token is dead; re-consent is needed before anything "
            "in the queue can be fetched"
        ) from error
    except Exception as error:
        # A database error's message can include bound health data. Log its type,
        # never its message or the pointer that produced it.
        logger.error(
            "fetch failed for %s (user %s): %s", data_type, user, type(error).__name__
        )
        raise

    result = "; ".join(str(found) for found in results) or "nothing to fetch"
    logger.info("fetched %s (user %s): %s", data_type, user, result)

    try:
        run_id = await request_rollup(payload, results)
    except Exception as error:
        logger.error(
            "rollup run not created for %s (user %s): %s",
            data_type,
            user,
            type(error).__name__,
        )
        raise
    if run_id is not None:
        logger.info("requested rollup run %s (user %s)", run_id, user)
    return result


async def request_rollup(
    payload: dict[str, Any], results: list[FetchResult]
) -> str | None:
    """Create a rollup run for the hours ``results`` wrote, if any.

    Returns the run's id once Prefect has created it, without waiting for it to
    finish, or ``None`` when nothing was written that the summaries are built
    from. Raises if the run could not be created, so the message stays
    unacknowledged.

    The idempotency key names the delivery and the hours, so a redelivered
    message does not start a second run, while a later notification for the
    same hours does start one.
    """
    spans = [found.hours for found in results if found.hours is not None]
    if not spans:
        return None
    span = spans[0]
    for other in spans[1:]:
        span = span.union(other)

    pointer = payload["pointer"]
    health_user_id = pointer["healthUserId"]
    key = ":".join(
        [
            "fetch",
            str(payload.get("notification_id")),
            str(pointer.get("dataType")),
            span.start.isoformat(),
            span.end.isoformat(),
        ]
    )
    run = await arun_deployment(
        ROLLUP_DEPLOYMENT,
        parameters={
            "health_user_id": health_user_id,
            "start": span.start.isoformat(),
            "end": span.end.isoformat(),
        },
        timeout=0,
        idempotency_key=key,
        as_subflow=False,
    )
    return str(run.id)


def _fetch_blocking(payload: dict[str, Any]) -> list[FetchResult]:
    """The synchronous unit: one session, one pointer, one commit.

    Everything blocking happens here, in one thread hop rather than several: a
    session, a token refresh, a paginated read and the upserts.
    """
    pointer = payload["pointer"]
    health_user_id = pointer.get("healthUserId")
    if not health_user_id:
        raise ValueError("change pointer named no user")

    with get_session() as session:
        user = build_user_repository(session).get(health_user_id)
        if user is None:
            # Not an error worth retrying: a notification for a user we have no
            # consent for cannot be acted on, and the row will not appear by
            # being asked again.
            thread_logger.info(
                "no consented user for {}", hashed_log_id(health_user_id)
            )
            return []

        return build_fetcher(session).fetch_pointer(user, pointer)


@flow(name="fetch-notifications", log_prints=True)
async def fetch_notifications() -> str:
    """Drain the queue, fetching what each message asks for.

    Takes no parameters on purpose: see the module docstring.
    """
    logger = get_run_logger()
    settings = get_settings()

    consumer = NotificationConsumer(settings.nats_url)
    await consumer.start()
    try:
        report = await consumer.drain_queue(_handle)
    finally:
        # Always, so a failed run does not leave a durable consumer holding a
        # connection the next run will queue behind.
        await consumer.stop()

    if report.failed or report.aborted:
        logger.warning("drained the notification queue: %s", report)
    else:
        logger.info("drained the notification queue: %s", report)
    return str(report)


async def _handle(payload: dict[str, Any]) -> None:
    """Hand one message to the task, letting failure propagate.

    The consumer acknowledges only if this returns normally, so raising here is
    how a message survives a failure.
    """
    await fetch_pointer(payload)


def deploy() -> None:
    """Register both deployments and serve them.

    ``serve()`` rather than a work pool and a separate worker: this is a
    single-user deployment, and a work pool adds a second process and a second
    state machine to manage for no benefit at this size. The process this starts
    both registers the deployment and executes its runs.

    The receiver and the backfill find both deployments by name, so nothing
    printed here needs copying into a setting.
    """
    # to_deployment returns a coroutine only when called from async code; here
    # it is synchronous, which its signature cannot express.
    serve(
        fetch_notifications.to_deployment(name=FETCHER_DEPLOYMENT_NAME),  # type: ignore[arg-type]
        rollup_heart_rate.to_deployment(name=ROLLUP_DEPLOYMENT_NAME),  # type: ignore[arg-type]
    )


if __name__ == "__main__":  # pragma: no cover -- an operator entry point
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "deploy":
        deploy()
    else:
        print(asyncio.run(fetch_notifications()))
