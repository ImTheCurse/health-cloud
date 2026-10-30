"""Arguments refused locally, before a request is ever sent.

Google's error for a malformed id or a plain-HTTP endpoint arrives long after
the wizard has announced what it is doing, so the client checks first.
"""

import pytest

from server.webhooks.error import SubscriberError
from server.webhooks.subscriber import SubscriberClient
from tests.webhooks.fakes import PROJECT, VALID_ENDPOINT, VALID_ID, FakeSession


@pytest.mark.parametrize(
    "bad_id", ["ab", "Health-Cloud", "health_cloud", "-health", "health-", "x" * 40]
)
def test_invalid_subscriber_ids_are_refused_before_any_request(bad_id):
    session = FakeSession()

    with pytest.raises(SubscriberError, match="invalid"):
        SubscriberClient(PROJECT, session).create(bad_id, VALID_ENDPOINT, "s")

    assert session.calls == []


@pytest.mark.parametrize(
    "bad_endpoint", ["http://example.com/hook", "http://localhost:8000/webhooks/health"]
)
def test_non_https_endpoints_are_refused(bad_endpoint):
    session = FakeSession()

    with pytest.raises(SubscriberError, match="https"):
        SubscriberClient(PROJECT, session).create(VALID_ID, bad_endpoint, "s")

    assert session.calls == []
