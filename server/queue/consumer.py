"""Pulling change pointers back off JetStream.

The other half of the durability contract. The receiver's job ends when the
broker confirms a message is persisted; this is what takes it from there, and the
rule that makes at-least-once mean something is that a message is acknowledged
**only after its upsert has committed**.

A pull consumer rather than a push subscription: the flow decides when it is
ready for work, which is what lets one run drain a burst and then exit instead of
holding a subscription open between runs.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import nats
from loguru import logger
from nats.aio.client import Client
from nats.aio.msg import Msg
from nats.errors import TimeoutError as NatsTimeoutError
from nats.js import JetStreamContext
from nats.js.api import AckPolicy, ConsumerConfig

from server.queue.const import (
    ACK_WAIT_SECONDS,
    CONNECT_TIMEOUT_SECONDS,
    CONSUMER_NAME,
    FETCH_BATCH_SIZE,
    MAX_DELIVER,
    PULL_TIMEOUT_SECONDS,
    STREAM_NAME,
    SUBJECT_PREFIX,
)
from server.queue.error import DrainAborted, QueueError
from server.queue.util import decode_notification


@dataclass(frozen=True)
class DrainReport:
    """What one drain did. Returned so the flow has something to report."""

    handled: int
    failed: int
    #: Why the run stopped early, if it did. Everything still queued is untouched.
    aborted: str | None = None

    def __str__(self) -> str:
        summary = f"{self.handled} handled" + (
            f", {self.failed} failed" if self.failed else ""
        )
        return summary + (f", stopped early: {self.aborted}" if self.aborted else "")


#: What the consumer hands each message to. Async because the work it wraps is,
#: and returning normally is what earns the ack.
Handler = Callable[[dict[str, Any]], Awaitable[None]]


class NotificationConsumer:
    """A durable pull consumer over the notification stream."""

    def __init__(
        self,
        url: str,
        stream: str = STREAM_NAME,
        subject_prefix: str = SUBJECT_PREFIX,
        durable: str = CONSUMER_NAME,
        batch_size: int = FETCH_BATCH_SIZE,
        ack_wait: float = ACK_WAIT_SECONDS,
        max_deliver: int = MAX_DELIVER,
        pull_timeout: float = PULL_TIMEOUT_SECONDS,
        connect_timeout: float = CONNECT_TIMEOUT_SECONDS,
    ) -> None:
        self._url = url
        self._stream = stream
        self._subject = f"{subject_prefix}.*"
        self._durable = durable
        self._batch_size = batch_size
        self._ack_wait = ack_wait
        self._max_deliver = max_deliver
        self._pull_timeout = pull_timeout
        self._connect_timeout = connect_timeout
        self._client: Client | None = None
        self._subscription: JetStreamContext.PullSubscription | None = None

    async def start(self) -> None:
        if self._client is not None:
            return
        client = await nats.connect(self._url, connect_timeout=self._connect_timeout)
        js = client.jetstream()
        subscription = await js.pull_subscribe(
            subject=self._subject,
            durable=self._durable,
            stream=self._stream,
            config=ConsumerConfig(
                durable_name=self._durable,
                # Every message is acknowledged individually, which is the whole
                # point: a batch-level ack would acknowledge work that failed.
                ack_policy=AckPolicy.EXPLICIT,
                ack_wait=self._ack_wait,
                max_deliver=self._max_deliver,
            ),
        )
        self._client, self._subscription = client, subscription
        logger.info(
            "consuming {} from stream {} as {}",
            self._subject,
            self._stream,
            self._durable,
        )

    async def stop(self) -> None:
        """Close the connection. Deliberately *not* a drain.

        The publisher drains because it may have publishes in flight that must
        reach the broker before the socket goes. A pull consumer has no such
        backlog: it asked for each batch explicitly and every ack was awaited, so
        there is nothing to flush.
        """
        client, subscription, self._client, self._subscription = (
            self._client,
            self._subscription,
            None,
            None,
        )
        if subscription is not None:
            try:
                await subscription.unsubscribe()
            except Exception as error:
                # Already gone, or the connection died first. Either way the
                # close below is what actually releases the socket.
                logger.debug("pull subscription was not unsubscribed: {}", error)
        if client is None or client.is_closed:
            return
        try:
            await client.close()
        except Exception as error:
            logger.warning("NATS did not close cleanly: {}", error)

    async def drain_queue(self, handle: Handler) -> DrainReport:
        """Hand every queued message to ``handle``, until the stream is empty.

        A message is acknowledged only once ``handle`` has returned normally. If
        it raises, the message is left alone: the broker redelivers it after
        ``ack_wait``, up to ``max_deliver`` times, so a transient failure costs a
        delay and a permanent one stops instead of looping.

        Draining rather than handling a single batch is what lets one run catch up
        after an outage, instead of needing one trigger per stranded message.

        A handler may raise ``DrainAborted`` to stop the whole run with everything
        still queued -- see that exception for why continuing would be worse than
        stopping.
        """
        handled = failed = 0
        while True:
            batch = await self._next_batch()
            if not batch:
                return DrainReport(handled, failed)
            for message in batch:
                try:
                    succeeded = await self._handle_one(message, handle)
                except DrainAborted as abort:
                    logger.warning("stopping the drain: {}", abort)
                    return DrainReport(handled, failed, aborted=str(abort))
                if succeeded:
                    handled += 1
                else:
                    failed += 1

    async def _handle_one(self, message: Msg, handle: Handler) -> bool:
        try:
            payload = decode_notification(message.data)
        except QueueError as error:
            # Unparseable is permanent: redelivering cannot make it readable. Term
            # stops the redelivery loop immediately rather than burning max_deliver
            # attempts on a message that will never work.
            logger.error("discarding an unreadable message: {}", error)
            await message.term()
            return False

        try:
            await handle(payload)
        except DrainAborted:
            # Not this message's fault and not a failure of it: it stays
            # unacknowledged and comes back when the cause is fixed.
            raise
        except Exception as error:
            # The type, never the message: a database failure stringifies with its
            # bound parameters, and those parameters are this delivery's health
            # data.
            logger.error("message handling failed: {}", type(error).__name__)
            return False

        await message.ack()
        return True

    async def _next_batch(self) -> list[Msg]:
        subscription = self._subscription
        if subscription is None:
            raise QueueError("consumer is not started")
        try:
            return await subscription.fetch(
                batch=self._batch_size, timeout=self._pull_timeout
            )
        except NatsTimeoutError:
            # An empty pull is how a drain discovers it is finished, not a fault.
            return []
