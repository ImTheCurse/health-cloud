"""The story of one request, accumulated while it runs.

Rather than scattering a line per thing that happens, each request builds a
single record that the middleware emits once, at the end.

The record lives on ``request.state``, so it is reached the same way any other
per-request value is: by being handed the request. Nothing here is ambient and
nothing is shared between requests -- two requests in flight hold two
unrelated objects, because each wraps its own ASGI scope.
"""

from dataclasses import dataclass, field
from typing import Any

from starlette.requests import Request

from server.observability.const import STATE_ATTRIBUTE
from server.observability.util import hashed_log_id


@dataclass
class RequestLog:
    """Everything worth knowing about a request, gathered as it happens."""

    request_id: str
    method: str
    path: str
    is_secure: bool
    x_forwarded_for: str | None
    user: str | None = None
    status: int | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    error: dict[str, str] | None = None


def attach(request: Request, record: RequestLog) -> None:
    """Make this record the one the rest of the request adds to."""
    setattr(request.state, STATE_ATTRIBUTE, record)


def get_request_log(request: Request) -> RequestLog | None:
    """The record for this request, or None if the middleware is not installed."""
    return getattr(request.state, STATE_ATTRIBUTE, None)


def add_event(request: Request, name: str, **fields: Any) -> None:
    """Record something worth knowing, to be emitted with the request.

    A no-op when no record is attached, so a route stays callable in a test
    that does not mount the middleware.
    """
    record = get_request_log(request)
    if record is not None:
        record.events.append({"event": name, **fields})


def set_user_to_request(request: Request, health_user_id: str) -> None:
    """Attach the (hashed) user this request turned out to be about."""
    record = get_request_log(request)
    if record is not None:
        record.user = hashed_log_id(health_user_id)


