"""When the consumer acknowledges, and when it refuses to.

The rule that makes at-least-once mean something: a message is acknowledged only
after the work it describes has committed. Everything here is about that ordering
and the two ways it can be broken -- acking too early, or acking something that
failed.
"""

import pytest

from server.queue.consumer import NotificationConsumer
from server.queue.error import DrainAborted, QueueError
from tests.queue.fakes import FakeMessage, FakeSubscription


def a_pointer(data_type="steps"):
    return {"notification_id": 1, "pointer": {"dataType": data_type, "intervals": []}}


def consumer_over(batches):
    """A consumer wired to a fake subscription, with no connection."""
    consumer = NotificationConsumer("nats://unused")
    consumer._subscription = FakeSubscription(batches)
    return consumer


async def test_a_handled_message_is_acknowledged():
    journal = []
    message = FakeMessage(a_pointer(), journal)

    report = await consumer_over([[message]]).drain_queue(_succeeds(journal))

    assert message.acked
    assert report.handled == 1


async def test_the_ack_comes_after_the_work():
    """Acking first would discard the message before the upsert committed, and
    Google's redelivery window is the only other copy."""
    journal = []
    message = FakeMessage(a_pointer(), journal)

    await consumer_over([[message]]).drain_queue(_succeeds(journal))

    assert journal == ["handled", "ack"]


async def test_a_failed_message_is_not_acknowledged():
    """Left alone, so the broker redelivers it after ack_wait."""
    journal = []
    message = FakeMessage(a_pointer(), journal)

    report = await consumer_over([[message]]).drain_queue(_raises(RuntimeError("no")))

    assert not message.acked
    assert not message.termed
    assert report.failed == 1


async def test_an_unreadable_message_is_terminated_not_retried():
    """Redelivering cannot make malformed JSON parse, so retrying it five times
    only delays the inevitable while occupying the consumer."""
    journal = []
    message = FakeMessage(None, journal, raw=b"{not json")

    report = await consumer_over([[message]]).drain_queue(_succeeds(journal))

    assert message.termed
    assert not message.acked
    assert report.failed == 1


async def test_a_message_with_no_pointer_is_also_terminated():
    journal = []
    message = FakeMessage({"notification_id": 1}, journal)

    await consumer_over([[message]]).drain_queue(_succeeds(journal))

    assert message.termed


async def test_the_drain_keeps_pulling_until_the_stream_is_empty():
    """One run catches up after an outage rather than needing one trigger per
    stranded message."""
    journal = []
    batches = [
        [FakeMessage(a_pointer(), journal) for _ in range(3)],
        [FakeMessage(a_pointer(), journal) for _ in range(2)],
    ]

    report = await consumer_over(batches).drain_queue(_succeeds(journal))

    assert report.handled == 5


async def test_an_empty_stream_is_not_a_failure():
    """A timeout on the first pull is how a run with nothing to do finishes."""
    report = await consumer_over([]).drain_queue(_succeeds([]))

    assert (report.handled, report.failed) == (0, 0)


async def test_one_failure_does_not_stop_the_rest_of_the_batch():
    """A poison message must not strand the messages behind it."""
    journal = []
    good = FakeMessage(a_pointer("steps"), journal)
    bad = FakeMessage(None, journal, raw=b"nonsense")
    also_good = FakeMessage(a_pointer("sleep"), journal)

    report = await consumer_over([[good, bad, also_good]]).drain_queue(_succeeds(journal))

    assert (report.handled, report.failed) == (2, 1)
    assert good.acked and also_good.acked


async def test_handler_failure_does_not_log_the_message_text(logs):
    """A database error stringifies with its bound parameters attached, and those
    parameters are the delivery's health data."""
    journal = []
    message = FakeMessage(a_pointer(), journal)
    secret = "sleep started at 23:04 for user 1234567890123456789"

    await consumer_over([[message]]).drain_queue(_raises(RuntimeError(secret)))

    assert logs, "nothing was logged, so this would pass vacuously"
    assert secret not in str([record.record["message"] for record in logs])


async def test_an_unstarted_consumer_refuses_to_drain():
    with pytest.raises(QueueError, match="not started"):
        await NotificationConsumer("nats://unused").drain_queue(_succeeds([]))


def _succeeds(journal):
    async def handle(payload):
        journal.append("handled")

    return handle


def _raises(error):
    async def handle(payload):
        raise error

    return handle


# --- stopping early ---


async def test_an_abort_stops_the_drain_immediately():
    """An expired token means nothing in the queue can succeed. Continuing would
    spend one of every message's five redelivery attempts discovering that, so a
    full queue would be burned through in minutes and then dropped."""
    journal = []
    first = FakeMessage(a_pointer(), journal)
    second = FakeMessage(a_pointer(), journal)
    third = FakeMessage(a_pointer(), journal)

    report = await consumer_over([[first, second, third]]).drain_queue(
        _raises(DrainAborted("the refresh token is dead"))
    )

    assert report.aborted
    assert not any(m.acked for m in (first, second, third))
    assert not any(m.termed for m in (first, second, third))


async def test_an_abort_leaves_later_batches_untouched():
    journal = []
    batches = [[FakeMessage(a_pointer(), journal)], [FakeMessage(a_pointer(), journal)]]
    subscription_batches = consumer_over(batches)

    await subscription_batches.drain_queue(_raises(DrainAborted("dead token")))

    # The second batch was never pulled, so its messages were never delivered and
    # spend none of their redelivery budget.
    assert subscription_batches._subscription.fetches == 1


async def test_an_abort_is_not_counted_as_a_failed_message():
    """It is not this message's fault, and it will be handled after re-consent."""
    journal = []
    message = FakeMessage(a_pointer(), journal)

    report = await consumer_over([[message]]).drain_queue(
        _raises(DrainAborted("dead token"))
    )

    assert (report.handled, report.failed) == (0, 0)


async def test_the_abort_reason_reaches_the_report():
    journal = []
    report = await consumer_over([[FakeMessage(a_pointer(), journal)]]).drain_queue(
        _raises(DrainAborted("re-consent needed"))
    )

    assert "re-consent needed" in str(report)
