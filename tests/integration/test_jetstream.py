"""What the broker actually guarantees.

The receiver answers 204 on the strength of a PubAck, so these tests check that
the acknowledgement means what the design assumes: the message is persisted, it
is retrievable, and it stays put until something acknowledges it.

Async, like the client and like the app -- these await exactly the calls a
running server makes.
"""

import json
import os

from nats.js.api import RetentionPolicy, StorageType

from server.queue.const import STREAM_NAME, SUBJECT_PREFIX
from tests.google_webhook import FAKE_HEALTH_USER_ID
from tests.integration.conftest import TEST_STREAM, TEST_SUBJECT_PREFIX

POINTER = {
    "dataType": "sleep",
    "operation": "UPSERT",
    "healthUserId": FAKE_HEALTH_USER_ID,
}
SLEEP_SUBJECT = f"{TEST_SUBJECT_PREFIX}.sleep"


async def test_a_publish_is_confirmed_with_a_sequence_number(publisher):
    """The PubAck is the receiver's licence to acknowledge Google."""
    ack = await publisher.publish(POINTER, notification_id=7)

    assert ack.stream == TEST_STREAM
    assert ack.seq >= 1


async def test_each_message_gets_its_own_sequence(publisher):
    first = await publisher.publish(POINTER, notification_id=7)
    second = await publisher.publish(POINTER, notification_id=7)

    # a batched delivery must not collapse into one
    assert second.seq > first.seq


async def test_a_published_message_can_be_read_back_intact(publisher):
    """What the fetch flow receives, checked end to end."""
    await publisher.publish(POINTER, notification_id=42)

    subscription = await publisher._js.pull_subscribe(
        SLEEP_SUBJECT, durable="test-consumer"
    )
    messages = await subscription.fetch(1, timeout=5)
    await messages[0].ack()

    assert json.loads(messages[0].data) == {
        "notification_id": 42,
        "pointer": POINTER,
    }


async def test_the_stream_is_file_backed_so_a_restart_keeps_the_work(publisher):
    """Memory storage would discard un-fetched notifications on restart."""
    info = await publisher._js.stream_info(TEST_STREAM)

    assert info.config.storage == StorageType.FILE


async def test_the_stream_is_a_work_queue_so_acknowledged_work_leaves(publisher):
    info = await publisher._js.stream_info(TEST_STREAM)

    assert info.config.retention == RetentionPolicy.WORK_QUEUE


async def test_an_unacknowledged_message_is_still_there(publisher):
    """At-least-once means the flow may fail without losing the work.

    The message is fetched and deliberately not acknowledged, so it must still
    be counted as unprocessed afterwards.
    """
    await publisher.publish(POINTER, notification_id=99)

    subscription = await publisher._js.pull_subscribe(
        SLEEP_SUBJECT, durable="unacked-consumer"
    )
    messages = await subscription.fetch(1, timeout=5)
    await messages[0].nak()

    info = await publisher._js.stream_info(TEST_STREAM)
    assert info.state.messages >= 1, "a nak'd message must not vanish"


async def test_starting_the_publisher_is_what_creates_the_stream(publisher):
    """No setup command to remember: the app's startup is the setup.

    The fixture only called start(). If the stream exists now, it exists
    because starting created it -- which is what the lifespan does on boot.
    """
    info = await publisher._js.stream_info(TEST_STREAM)

    assert info.config.name == TEST_STREAM
    assert info.config.subjects == [f"{TEST_SUBJECT_PREFIX}.*"]


async def test_creating_the_stream_twice_is_harmless(publisher):
    """Every boot runs it, so it has to be idempotent rather than first-run only."""
    before = (await publisher._js.stream_info(TEST_STREAM)).created

    await publisher._configure_stream(publisher._js)

    assert (await publisher._js.stream_info(TEST_STREAM)).created == before


async def test_the_tests_cannot_see_the_application_stream(publisher):
    """Real notifications arrive while the suite runs, so isolation matters.

    The app publishes to `health.notifications.*` in the `health` stream; the
    tests own a differently named stream whose subject filter cannot match
    those, so a sync landing mid-test can neither be counted here nor be
    consumed by a test's consumer.
    """

    info = await publisher._js.stream_info(TEST_STREAM)

    assert TEST_STREAM != STREAM_NAME
    assert not any(s.startswith(SUBJECT_PREFIX) for s in info.config.subjects)
    assert str(os.getpid()) in TEST_STREAM, "two runs must not share a stream"
