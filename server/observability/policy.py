"""Per-route logging policy.

The policy lives on the route it governs, as a decorator, so it cannot drift
out of sync the way a list of paths kept elsewhere would.
"""

from collections.abc import Callable
from typing import Any

from server.observability.const import ALWAYS, POLICY_ATTRIBUTE, QUIET


def log_policy(policy: str) -> Callable:
    """Mark a route's logging policy.

    Example:
        >>> @log_policy(QUIET)
        ... def healthz() -> dict:
        ...     return {"status": "ok"}
        >>> policy_for(healthz)
        'quiet'
    """
    if policy not in (ALWAYS, QUIET):
        raise ValueError(f"unknown log policy: {policy!r}")

    def decorate(endpoint: Callable) -> Callable:
        setattr(endpoint, POLICY_ATTRIBUTE, policy)
        return endpoint

    return decorate


def policy_for(endpoint: Any) -> str:
    """The policy a route declared, defaulting to logging everything.

    Defaulting to ALWAYS means a quiet route is always visible in the source;
    a new route is never quietened just because nobody thought about it.
    """
    return getattr(endpoint, POLICY_ATTRIBUTE, ALWAYS)
