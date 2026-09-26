"""The publisher's behaviour around its own connection state.

No broker is involved here -- these are the cases that must not raise something
unhelpful when the connection is absent.
"""

import pytest

from server.queue.error import PublishError, QueueError
from server.queue.publisher import NotificationPublisher


@pytest.fixture
def unstarted():
    return NotificationPublisher("nats://example.invalid:4222")


async def test_publishing_before_start_raises_rather_than_silently_dropping(unstarted):
    with pytest.raises(PublishError):
        await unstarted.publish({"dataType": "steps"}, notification_id=1)


async def test_a_publish_failure_is_a_queue_error_so_the_route_can_answer_503(unstarted):
    """The route catches QueueError; a subclass that escaped it would 500."""
    with pytest.raises(QueueError):
        await unstarted.publish({"dataType": "steps"}, notification_id=1)


def test_an_unstarted_publisher_is_not_connected(unstarted):
    assert unstarted.connected() is False


async def test_stopping_an_unstarted_publisher_is_harmless(unstarted):
    """Shutdown runs in a finally block, including when startup failed."""
    await unstarted.stop()

    assert unstarted.connected() is False


class StubClient:
    """A client that fails to drain, the way a reconnecting one does."""

    def __init__(self, drain_error: Exception | None = None) -> None:
        self.drain_error = drain_error
        self.drained = False
        self.closed = False

    @property
    def is_closed(self) -> bool:
        return self.closed

    @property
    def is_connected(self) -> bool:
        return not self.closed

    async def drain(self) -> None:
        self.drained = True
        if self.drain_error:
            raise self.drain_error

    async def close(self) -> None:
        self.closed = True


async def test_a_connection_that_cannot_drain_is_still_closed(unstarted):
    """drain() raises while reconnecting, and dropping the reference there
    would leak the socket for the life of the process."""
    client = StubClient(drain_error=RuntimeError("connection is reconnecting"))
    unstarted._client = client

    await unstarted.stop()

    assert client.drained
    assert client.closed, "the socket was left open"


async def test_a_drained_connection_is_not_closed_twice(unstarted):
    """drain() closes on success, so close() would raise ConnectionClosedError."""

    class DrainsCleanly(StubClient):
        async def drain(self) -> None:
            self.drained = True
            self.closed = True  # what the real client does

    client = DrainsCleanly()
    unstarted._client = client

    await unstarted.stop()

    assert client.drained


async def test_stopping_leaves_the_publisher_consistently_stopped(unstarted):
    """Even when shutdown went badly, it must not look half-connected."""
    unstarted._client = StubClient(drain_error=RuntimeError("boom"))

    await unstarted.stop()

    assert unstarted.connected() is False
    assert unstarted._js is None
