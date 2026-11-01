"""The audit row against real Postgres.

The body column is encrypted JSON. Whether a delivery actually round-trips
through it is not something a double can answer.
"""

import datetime as dt
import json

from sqlmodel import select

from server.models.notification import RawNotification
from tests.google_webhook import BATCHED_NOTIFICATION


def a_row(**overrides):
    values = {
        "received_at": dt.datetime.now(dt.UTC),
        "request_id": "req-1",
        "body": json.loads(BATCHED_NOTIFICATION),
        "pointer_count": 2,
    }
    return RawNotification(**{**values, **overrides})


def test_a_delivery_round_trips_through_encryption(session):
    """Nested structure, lists and all, must come back unchanged."""
    session.add(a_row())
    session.commit()

    stored = session.exec(select(RawNotification)).one()

    assert stored.body == json.loads(BATCHED_NOTIFICATION)
    assert stored.body[0]["data"]["intervals"][0]["physicalTimeInterval"]["startTime"]


def test_the_primary_key_is_generated_so_messages_can_reference_it(session):
    """The route puts this id into every message it publishes."""
    row = a_row()
    assert row.id is None

    session.add(row)
    session.commit()
    session.refresh(row)

    assert isinstance(row.id, int)


def test_timestamps_come_back_timezone_aware(session):
    """A naive timestamp here would silently mean 'some local time, somewhere'."""
    session.add(a_row())
    session.commit()

    stored = session.exec(select(RawNotification)).one()

    assert stored.received_at.tzinfo is not None


def test_the_log_is_append_only_in_practice(session):
    """Two identical deliveries are two rows.

    Delivery is at-least-once and a duplicate is indistinguishable from a
    genuine correction, so nothing here may collapse them.
    """
    session.add(a_row())
    session.add(a_row())
    session.commit()

    assert len(session.exec(select(RawNotification)).all()) == 2


def test_each_test_starts_with_an_empty_table(session):
    """Proves the fixture's isolation, which the tests above depend on.

    Written after rows from one test were visible in the next: without this,
    a counting assertion silently measures the whole session's history.
    """
    assert session.exec(select(RawNotification)).all() == []
