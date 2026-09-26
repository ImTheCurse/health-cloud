"""The story of one request, accumulated while it runs.

Rather than scattering a line per thing that happens, each request builds a
single record that the middleware emits once, at the end.

The record lives on ``request.state`` for the life of the request, and routes
receive it the way they receive anything else -- as a declared dependency. That
keeps it out of the route's hands as a `Request` object it would otherwise have
no use for, and nothing here is ambient: two requests in flight hold two
unrelated records, because each wraps its own ASGI scope.
"""

from dataclasses import dataclass, field
from typing import Annotated, Any

from fastapi import Depends
from starlette.requests import Request

from server.observability.const import STATE_ATTRIBUTE
from server.observability.util import hashed_log_id


@dataclass
class RequestLog:
    """Everything worth knowing about a request, gathered as it happens.

    The data and the ways of adding to it live together: the record is created
    by the middleware, changed only through these methods, and read only when it
    is emitted, so splitting it into a value and a manipulator would mean two
    objects that always travel together.
    """

    #: None only for a detached record -- see `unlogged()`.
    request_id: str | None
    method: str
    path: str
    is_secure: bool
    x_forwarded_for: str | None
    user: str | None = None
    status: int | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    error: dict[str, str] | None = None

    @classmethod
    def unlogged(cls) -> "RequestLog":
        """A record for a request nothing is going to emit.

        Handed to a route when the middleware is not mounted, which is the
        normal case in a test that exercises a route directly. Adding to it is
        harmless rather than special-cased: nothing emits it, so it is discarded
        with the request. That is why no method here needs to ask whether it is
        real.
        """
        return cls(
            request_id=None,
            method="",
            path="",
            is_secure=False,
            x_forwarded_for=None,
        )

    def attach(self, request: Request) -> None:
        """Make this the record the rest of the request adds to."""
        setattr(request.state, STATE_ATTRIBUTE, self)

    def add_event(self, name: str, **fields: Any) -> None:
        """Record something worth knowing, to be emitted with the request."""
        self.events.append({"event": name, **fields})

    def set_user(self, health_user_id: str) -> None:
        """Attach the (hashed) user this request turned out to be about."""
        self.user = hashed_log_id(health_user_id)


def get_request_log(request: Request) -> RequestLog:
    """The record for this request, or a detached one if none is attached.

    Never returns None: a caller that had to check would be checking on every
    single line it logs.
    """
    record = getattr(request.state, STATE_ATTRIBUTE, None)
    return record if isinstance(record, RequestLog) else RequestLog.unlogged()


#: What a route declares to get its own record, the same way it declares a
#: database session.
RequestLogDep = Annotated[RequestLog, Depends(get_request_log)]
