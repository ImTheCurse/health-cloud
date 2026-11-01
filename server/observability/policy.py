"""Per-route logging policy.

The policy lives on the route it governs, as a decorator, so it cannot drift
out of sync the way a list of paths kept elsewhere would.
"""

from collections.abc import Callable
from typing import Any

from server.observability.const import POLICY_ATTRIBUTE, LogPolicy


def log_policy(policy: LogPolicy) -> Callable:
    """Mark a route's logging policy.

    Example:
        >>> @log_policy(LogPolicy.QUIET)
        ... def healthz() -> dict:
        ...     return {"status": "ok"}
        >>> policy_for(healthz) is LogPolicy.QUIET
        True
    """
    # Raises ValueError for anything that is not a policy, which is the whole
    # reason this is an enum.
    policy = LogPolicy(policy)

    def decorate(endpoint: Callable) -> Callable:
        setattr(endpoint, POLICY_ATTRIBUTE, policy)
        return endpoint

    return decorate


def policy_for(endpoint: Any) -> LogPolicy:
    """The policy a route declared, defaulting to logging everything.

    Defaulting to ALWAYS means a quiet route is always visible in the source;
    a new route is never quietened just because nobody thought about it.
    """
    return getattr(endpoint, POLICY_ATTRIBUTE, LogPolicy.ALWAYS)
