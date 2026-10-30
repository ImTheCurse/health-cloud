"""What the receiver does with a notification it has accepted.

The durability contract is an *ordering*, not a transaction: record, publish,
only then acknowledge. These tests are about that order and about what happens
when a step fails -- the cases that decide whether a notification can be lost.
"""

import json

from server.webhooks.const import SIGNATURE_HEADER, WEBHOOK_PATH
from tests.conftest import logged_text
from tests.google_webhook import (
    AUTH,
    BATCHED_NOTIFICATION,
    FAKE_HEALTH_USER_ID,
    NOTIFICATION,
    sign,
)


def deliver(client, signer, body=NOTIFICATION):
    return client.post(
        WEBHOOK_PATH,
        content=body,
        headers={"Authorization": AUTH, SIGNATURE_HEADER: sign(signer, body)},
    )


def test_the_audit_row_commits_before_anything_is_published(signer_and_client, journal):
    """The order is the guarantee.

    Published first, work could be queued with nothing recording what asked for
    it. All three doubles write to one journal, so the sequence is visible rather
    than inferred.
    """
    signer, client = signer_and_client

    deliver(client, signer)

    assert journal.steps() == ["commit", "publish", "trigger"]


def test_prefect_is_asked_last_of_all(signer_and_client, journal):
    """The trigger runs in a background task, after the response is sent.

    It is last because it must not be able to delay the acknowledgement: the
    notification is already persisted in the broker by the time it runs, so the
    fetch is guaranteed by the queue rather than by this call succeeding.
    """
    signer, client = signer_and_client

    deliver(client, signer)

    assert journal.steps()[-1] == "trigger"


def test_one_trigger_per_delivery_not_per_pointer(signer_and_client, trigger):
    """A run drains the whole queue, so a batched delivery needs one doorbell."""
    signer, client = signer_and_client

    deliver(client, signer, BATCHED_NOTIFICATION)

    assert trigger.calls == 1


def test_one_message_is_published_per_change_pointer(signer_and_client, publisher):
    """Google batches, so a delivery is not one unit of work."""
    signer, client = signer_and_client

    deliver(client, signer, BATCHED_NOTIFICATION)

    assert [pointer["dataType"] for _, pointer in publisher.published] == [
        "steps",
        "sleep",
    ]


def test_a_batched_delivery_is_recorded_as_one_row(signer_and_client, session):
    """The audit log records deliveries; the queue records work."""
    signer, client = signer_and_client

    deliver(client, signer, BATCHED_NOTIFICATION)

    assert len(session.added) == 1
    assert session.added[0].pointer_count == 2


def test_the_recorded_body_is_exactly_what_arrived(signer_and_client, session):
    """The audit row is a record of the delivery, envelopes and all."""
    signer, client = signer_and_client

    deliver(client, signer, BATCHED_NOTIFICATION)

    row = session.added[0]
    assert row.body == json.loads(BATCHED_NOTIFICATION)
    assert row.received_at is not None
    assert row.request_id, "the row must be traceable to the request's log line"


def test_every_message_carries_the_row_it_belongs_to(signer_and_client, publisher):
    """A message is self-contained, so the flow never reads the audit table."""
    signer, client = signer_and_client

    deliver(client, signer)

    notification_id, pointer = publisher.published[0]
    assert notification_id == 1
    assert pointer["healthUserId"] == FAKE_HEALTH_USER_ID
    assert pointer["dataType"] == "steps"


def test_nothing_is_published_when_the_row_cannot_be_recorded(
    signer_and_client, session, publisher
):
    """Nothing is half-done: no row means no work queued."""
    signer, client = signer_and_client
    session.fail = True

    response = deliver(client, signer)

    assert response.status_code == 503
    assert publisher.published == []
    assert session.rolled_back


def test_a_delivery_is_not_acknowledged_when_the_broker_refuses(
    signer_and_client, publisher
):
    """503, not 204: Google must redeliver rather than consider this done."""
    signer, client = signer_and_client
    publisher.fail = True

    response = deliver(client, signer)

    assert response.status_code == 503


def test_a_broker_failure_leaves_the_audit_row_in_place(
    signer_and_client, publisher, session
):
    """Deliberate: the delivery did arrive, and that is true regardless.

    The redelivery adds a second row, which is harmless -- the log is
    append-only and dedupe happens at the data level.
    """
    signer, client = signer_and_client
    publisher.fail = True

    deliver(client, signer)

    assert len(session.added) == 1
    assert not session.rolled_back


def test_only_a_fully_successful_delivery_is_acknowledged(signer_and_client, journal):
    signer, client = signer_and_client

    response = deliver(client, signer)

    assert response.status_code == 204
    assert journal.steps() == ["commit", "publish", "trigger"]


def test_a_database_failure_does_not_put_the_payload_in_the_log(
    signer_and_client, session, logs
):
    """SQLAlchemy errors stringify with their bound parameters attached.

    Those parameters are the delivery itself, so logging the message rather
    than the exception type would leak health data into the log on every
    database wobble -- the one place this module works hardest to keep it out
    of. The fake raises an exception shaped like the real one.
    """
    from sqlalchemy.exc import StatementError

    signer, client = signer_and_client

    def explode() -> None:
        raise StatementError(
            "insert failed",
            "INSERT INTO raw_notifications (body) VALUES (%(body)s)",
            {"body": {"healthUserId": FAKE_HEALTH_USER_ID}},
            Exception(),
        )

    session.commit = explode

    response = deliver(client, signer)

    assert response.status_code == 503
    assert logs, "nothing was logged, so this test would pass vacuously"
    revealed = logged_text(logs)
    assert FAKE_HEALTH_USER_ID not in revealed
    assert "INSERT INTO" not in revealed, "the statement must not be logged either"
    assert "StatementError" in revealed, "but the failure must still be diagnosable"


def test_a_refused_trigger_still_acknowledges_the_delivery(
    signer_and_client, journal, trigger
):
    """Prefect being down must not turn a queued notification into a 503.

    This is the whole reason the trigger is a background task whose failure is
    swallowed: the message is already persisted, and answering anything but 204
    would make Google redeliver work that is not lost.
    """
    signer, client = signer_and_client
    trigger.fail = True

    response = deliver(client, signer)

    assert response.status_code == 204
    assert journal.steps() == ["commit", "publish", "trigger"]


def test_a_refused_trigger_does_not_log_a_traceback(signer_and_client, trigger, logs):
    """It is an expected condition, not a crash: one warning, no stack."""
    signer, client = signer_and_client
    trigger.fail = True

    deliver(client, signer)

    warnings = [record for record in logs if record.record["level"].name == "WARNING"]
    assert any("could not start a fetcher run" in str(r.record["message"]) for r in warnings)
