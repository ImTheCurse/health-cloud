"""One structured line per request.

Written as the `@app.middleware("http")` function FastAPI documents: it is
handed the request and a `call_next`, which is what makes `request.state` the
natural place to keep the record while the request runs.
"""

import time
import uuid

from fastapi import Request
from loguru import logger

from server.config.const import LOCAL_ENV
from server.config.settings import get_settings
from server.observability.const import REQUEST_ID_HEADER, LogPolicy
from server.observability.context import RequestLog
from server.observability.policy import policy_for
from server.observability.util import is_secure


async def log_requests(request: Request, call_next):
    """Gather the request into one record and emit it when it finishes."""
    record = RequestLog(
        request_id=uuid.uuid4().hex,
        method=request.method,
        path=request.url.path,
        is_secure=is_secure(request),
        x_forwarded_for=request.headers.get("X-Forwarded-For"),
    )
    record.attach(request)
    started = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception as exc:
        # The post's "message" and "cause". Losing the line because the
        # request failed would hide exactly the requests worth seeing.
        record.error = {"message": str(exc), "cause": type(exc).__name__}
        raise
    else:
        record.status = response.status_code
        response.headers[REQUEST_ID_HEADER] = record.request_id
        return response
    finally:
        _emit(record, request, time.perf_counter() - started)


def _emit(record: RequestLog, request: Request, elapsed: float) -> None:
    duration_ms = round(elapsed * 1000, 2)
    payload = {
        "request_id": record.request_id,
        "method": record.method,
        "path": record.path,
        "status": record.status,
        "duration_ms": duration_ms,
        "is_secure": record.is_secure,
        "x_forwarded_for": record.x_forwarded_for,
        "user": record.user,
        "events": record.events,
        "error": record.error,
    }
    message = f"{record.method} {record.path} {record.status} in {duration_ms}ms"
    logger.bind(**payload).log(_level(record, request), message)


def _level(record: RequestLog, request: Request) -> str:
    """How loudly to report this request.

    Everything is INFO locally, and on a route that has not opted out. A quiet
    route still speaks up when it has something to say -- an error, an
    exception, or a domain event -- and is otherwise DEBUG.
    """
    if record.error is not None:
        return "ERROR"
    if get_settings().environment == LOCAL_ENV:
        return "INFO"
    if policy_for(request.scope.get("endpoint")) == LogPolicy.ALWAYS:
        return "INFO"
    interesting = (record.status or 0) >= 400 or record.events
    return "INFO" if interesting else "DEBUG"
