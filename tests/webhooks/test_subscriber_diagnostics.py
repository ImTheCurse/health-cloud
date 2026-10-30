"""Turning Google's replies into something the operator can act on.

A bare FAILED_PRECONDITION or 403 says nothing about which of the several
possible causes applies, so the client translates them.
"""

import pytest

from server.webhooks.error import SubscriberError
from server.webhooks.subscriber import SubscriberClient, describe
from tests.webhooks.fakes import (
    PROJECT,
    VALID_ENDPOINT,
    VALID_ID,
    FakeResponse,
    FakeSession,
    subscriber_payload,
)


def test_create_surfaces_an_operation_error():
    session = FakeSession(FakeResponse(payload={"error": {"message": "nope"}}))

    with pytest.raises(SubscriberError, match="nope"):
        SubscriberClient(PROJECT, session).create(VALID_ID, VALID_ENDPOINT, "s")


def test_failed_handshake_explains_what_the_endpoint_must_do():
    session = FakeSession(
        FakeResponse(
            status_code=400,
            payload={
                "error": {"status": "FAILED_PRECONDITION", "message": "bad endpoint"}
            },
        )
    )

    with pytest.raises(SubscriberError, match="401/403"):
        SubscriberClient(PROJECT, session).create(VALID_ID, VALID_ENDPOINT, "s")


def test_permission_denied_names_the_missing_role():
    session = FakeSession(
        FakeResponse(status_code=403, payload={"error": {"message": "denied"}})
    )

    with pytest.raises(SubscriberError, match="Google Health API Admin"):
        SubscriberClient(PROJECT, session).list()


def test_describe_does_not_flag_a_subscriber_google_reports_no_state_for():
    """Regression: a missing state is normal, not a failure.

    Defaulting it to UNKNOWN and flagging [!!] made a registration that had
    genuinely passed Google's handshake print as though it had failed.
    """
    rendered = describe(subscriber_payload())

    assert "[ok]" in rendered
    assert "not reported by Google" in rendered


def test_describe_flags_an_unverified_subscriber():
    """If Google ever does send a state, a bad one must stand out."""
    assert "[!!]" in describe(subscriber_payload("UNVERIFIED"))
    assert "[ok]" in describe(subscriber_payload("ACTIVE"))


def test_describe_flags_an_endpoint_with_no_secret():
    """Without a registered secret the receiver would 401 every delivery."""
    assert "[!!]" in describe(subscriber_payload(secret_set=False))
