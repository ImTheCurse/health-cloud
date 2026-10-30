"""Helpers for building a request's log record."""

import hashlib

from starlette.requests import Request

from server.observability.const import LOG_ID_BYTES


def hashed_log_id(health_user_id: str) -> str:
    """A short, stable, non-reversible handle for a user.

    Deliberately a pure function of the id rather than a stored column: it can
    always be recomputed to work out which user a log line refers to, so there
    is nothing to migrate and nothing extra to keep in the database.

    Example:
        >>> hashed_log_id("1234567890123456789") == hashed_log_id("1234567890123456789")
        True
        >>> len(hashed_log_id("1234567890123456789"))
        6
    """
    digest = hashlib.sha256(health_user_id.encode()).digest()
    return digest[:LOG_ID_BYTES].hex()


def is_secure(request: Request) -> bool:
    """Whether the caller reached us over TLS.

    Behind a tunnel the connection to the app is plain HTTP, so the forwarded
    protocol is what the caller actually used.
    """
    forwarded = request.headers.get("X-Forwarded-Proto")
    if forwarded:
        return forwarded == "https"
    return request.url.scheme == "https"
