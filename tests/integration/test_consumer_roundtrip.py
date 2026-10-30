"""Publisher to consumer, against real NATS.

The properties here are the broker's, not ours, so a double cannot show them: that
an acknowledged message leaves a work-queue stream, that an unacknowledged one
comes back, and that the durable consumer's position survives being reconnected.
"""

import asyncio

import pytest

from tests.google_webhook import FAKE_HEALTH_USER_ID


def a_pointer(data_type="steps"):
    return {
        "dataType": data_type,
        "operation": "UPSERT",
        "healthUserId": FAKE_HEALTH_USER_ID,
        "intervals": [],
    }


async def test_a_published_pointer_comes_back_to_the_consumer(publisher, consumer):
    await publisher.publish(a_pointer("steps"), notification_id=1)

    seen = []

    async def handle(payload):
        seen.append(payload)

    report = await consumer.drain_queue(handle)

    assert report.handled == 1
    assert seen[0]["pointer"]["dataType"] == "steps"
    assert seen[0]["notification_id"] == 1


async def test_every_pointer_of_a_batch_arrives(publisher, consumer):
    for index, data_type in enumerate(["steps", "sleep", "distance"]):
        await publisher.publish(a_pointer(data_type), notification_id=index)

    seen = []

    async def handle(payload):
        seen.append(payload["pointer"]["dataType"])

    await consumer.drain_queue(handle)

    assert sorted(seen) == ["distance", "sleep", "steps"]


async def test_an_acknowledged_message_leaves_the_stream(publisher, consumer):
    """What makes it a work queue rather than a log: once the upsert committed and
    the message was acked, it is gone, so a second run does not redo the work."""
    await publisher.publish(a_pointer(), notification_id=1)

    async def handle(payload):
        return None

    first = await consumer.drain_queue(handle)
    second = await consumer.drain_queue(handle)

    assert (first.handled, second.handled) == (1, 0)


async def test_an_unacknowledged_message_is_redelivered(publisher, consumer):
    """The other half of the durability contract. The receiver's 204 promised the
    message was persisted; this is what makes that promise pay out when the work
    fails."""
    await publisher.publish(a_pointer(), notification_id=1)

    attempts = []

    async def fails(payload):
        attempts.append(payload)
        raise RuntimeError("the upsert did not commit")

    await consumer.drain_queue(fails)
    assert len(attempts) == 1

    # ack_wait is 2s on the test consumer, so the broker hands it back after that.
    await asyncio.sleep(2.5)

    async def succeeds(payload):
        attempts.append(payload)

    report = await consumer.drain_queue(succeeds)

    assert report.handled == 1
    assert len(attempts) == 2


async def test_an_unreadable_message_does_not_come_back(publisher, consumer):
    """Terminated rather than retried: redelivery cannot make it parseable, and
    five attempts at nonsense only delay everything behind it."""
    js = publisher._js
    await js.publish(f"{consumer._subject.rsplit('.', 1)[0]}.steps", b"{not json")

    async def handle(payload):  # pragma: no cover -- must never be reached
        raise AssertionError("an unreadable message reached the handler")

    first = await consumer.drain_queue(handle)
    await asyncio.sleep(2.5)
    second = await consumer.drain_queue(handle)

    assert first.failed == 1
    assert second.handled == 0 and second.failed == 0
