"""Which types a backfill fetches when none are named."""

from server.cli import backfill_types
from server.health.const import LIST_UNSUPPORTED
from server.webhooks.const import DATA_TYPES, SYSTEM_EVENTS


def test_every_fetchable_subscribed_type_is_backfilled():
    types = backfill_types()

    assert "heart-rate" in types
    assert "oxygen-saturation" in types
    assert set(types) <= set(DATA_TYPES)


def test_account_events_are_not_backfilled():
    assert not SYSTEM_EVENTS & set(backfill_types())


def test_types_without_list_are_skipped_except_floors():
    types = set(backfill_types())

    assert "floors" in types
    assert not (LIST_UNSUPPORTED - {"floors"}) & types
