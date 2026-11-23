"""The heart-rate rollup flow.

Rebuilds the hourly heart-rate summaries for one user over a span of local
hours, from the samples already stored. The fetcher flow starts a run for every
heart-rate or time-in-zone message before acknowledging it, and the backfill
starts one when it finishes, so the summaries follow the samples without either
caller waiting for them.

**Retried by Prefect, unlike the fetch.** The fetch is retried by JetStream
redelivering its message. Nothing redelivers a rollup run, so the run retries
itself. The work is a rebuild, so a retry repeats it harmlessly.
"""

import datetime as dt

import anyio.to_thread
from prefect import flow, get_run_logger

from server.db.session import get_session
from server.observability.util import hashed_log_id
from server.rollup.hours import HeartRateHours, HourSpan

#: Attempts after the first, and the wait before each: long enough for a
#: restarting database to come back.
RETRIES = 3
RETRY_DELAY_SECONDS = 60


@flow(
    name="rollup-heart-rate",
    retries=RETRIES,
    retry_delay_seconds=RETRY_DELAY_SECONDS,
)
async def rollup_heart_rate(
    health_user_id: str, start: dt.datetime, end: dt.datetime
) -> str:
    """Rebuild one user's hourly summaries for the local hours ``[start, end)``."""
    logger = get_run_logger()
    span = HourSpan(start, end)
    user = hashed_log_id(health_user_id)

    def rebuild() -> int:
        with get_session() as session:
            return HeartRateHours(session).rebuild_in_chunks(health_user_id, span)

    try:
        written = await anyio.to_thread.run_sync(rebuild)
    except Exception as error:
        # A database error's message can include bound health data.
        logger.error("rollup failed for user %s: %s", user, type(error).__name__)
        raise

    result = f"{written} hour(s) from {span.start} to {span.end}"
    logger.info("rolled up heart rate for user %s: %s", user, result)
    return result
