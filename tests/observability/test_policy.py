"""The per-route logging policy."""

import pytest

from server.observability.const import ALWAYS, QUIET
from server.observability.policy import log_policy, policy_for


def test_a_route_that_says_nothing_is_logged_in_full():
    """The default is ALWAYS so quietness is never silently inherited.

    A new route should be visible from the day it is written; going quiet is
    a decision someone makes in the source.
    """

    def endpoint() -> None: ...

    assert policy_for(endpoint) == ALWAYS


def test_a_route_can_opt_into_being_quiet():
    @log_policy(QUIET)
    def endpoint() -> None: ...

    assert policy_for(endpoint) == QUIET


def test_the_decorator_returns_the_same_callable():
    """It tags the endpoint; it must not wrap it, or FastAPI loses the signature."""

    def endpoint() -> str:
        return "value"

    assert log_policy(QUIET)(endpoint) is endpoint
    assert endpoint() == "value"


def test_an_unknown_policy_is_refused_at_import_time():
    """A typo should fail when the module loads, not silently log everything."""
    with pytest.raises(ValueError, match="unknown log policy"):
        log_policy("verbose")


def test_an_unrouted_request_falls_back_to_always():
    """scope['endpoint'] is absent when nothing matched, e.g. a 404."""
    assert policy_for(None) == ALWAYS
