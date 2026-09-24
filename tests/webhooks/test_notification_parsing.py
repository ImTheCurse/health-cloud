"""Reading the change pointers out of a delivery.

The shape here is not a guess: it was captured from live traffic after the
first real notifications were refused with 403. The parser had been written
against a bare JSON object, and Google sends an array of envelopes.
"""

import json

import pytest

from server.webhooks.error import NotificationError
from server.webhooks.receiver import parse_notification
from tests.google_webhook import (
    BARE_NOTIFICATION,
    BATCHED_NOTIFICATION,
    FAKE_HEALTH_USER_ID,
    NOTIFICATION,
)


def test_a_real_delivery_yields_its_change_pointer():
    """Regression: an array of envelopes used to be refused outright."""
    pointers = parse_notification(NOTIFICATION)

    assert len(pointers) == 1
    assert pointers[0]["dataType"] == "steps"
    assert pointers[0]["operation"] == "UPSERT"
    assert pointers[0]["healthUserId"] == FAKE_HEALTH_USER_ID


def test_the_envelope_is_unwrapped():
    """The pointer lives under "data"; nothing downstream should see the wrapper."""
    assert "data" not in parse_notification(NOTIFICATION)[0]


def test_a_batched_delivery_yields_every_pointer():
    """One delivery can carry several, and dropping the tail loses data."""
    pointers = parse_notification(BATCHED_NOTIFICATION)

    assert [p["dataType"] for p in pointers] == ["steps", "sleep"]


def test_a_bare_object_is_still_accepted():
    """The documented example shows one, so it must not be refused."""
    pointers = parse_notification(BARE_NOTIFICATION)

    assert len(pointers) == 1
    assert pointers[0]["dataType"] == "steps"


def test_intervals_survive_intact():
    """The fetcher queries by these, so they must reach it unaltered."""
    interval = parse_notification(NOTIFICATION)[0]["intervals"][0]

    assert interval["physicalTimeInterval"]["startTime"] == "2026-01-02T09:00:00Z"


def test_an_unparseable_body_is_reported_as_a_notification_problem():
    """Not a SignatureError: the signature was fine, our reading was not."""
    with pytest.raises(NotificationError, match="not valid JSON"):
        parse_notification(b"not json")


def test_an_empty_array_is_refused():
    with pytest.raises(NotificationError, match="no change pointers"):
        parse_notification(b"[]")


def test_a_non_object_entry_is_refused():
    with pytest.raises(NotificationError, match="not a JSON object"):
        parse_notification(json.dumps(["nope"]).encode())
