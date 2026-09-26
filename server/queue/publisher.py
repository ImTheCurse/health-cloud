"""Publishing change pointers to JetStream.

``nats-py`` is asyncio-native and so is FastAPI, so this holds no event loop of
its own: the connection is opened in the app's lifespan, on the loop uvicorn is
already running, and the receiver awaits its publishes directly.
"""

import json
from typing import Any

import nats
from loguru import logger
from nats.aio.client import Client
from nats.js import JetStreamContext
from nats.js.api import RetentionPolicy, StorageType, StreamConfig
from nats.js.errors import NotFoundError

from server.queue.const import (
    CONNECT_TIMEOUT_SECONDS,
    PUBLISH_TIMEOUT_SECONDS,
    STREAM_NAME,
    SUBJECT_PREFIX,
)
from server.queue.error import PublishError
from server.queue.util import subject_for


class NotificationPublisher:
    """A JetStream connection held open for the life of the process."""

    def __init__(
        self,
        url: str,
        stream: str = STREAM_NAME,
        subject_prefix: str = SUBJECT_PREFIX,
        publish_timeout: float = PUBLISH_TIMEOUT_SECONDS,
        connect_timeout: float = CONNECT_TIMEOUT_SECONDS,
        allow_direct: bool = False,
    ) -> None:
        self._url = url
        self._stream = stream
        self._subject_prefix = subject_prefix
        self._subjects = (f"{subject_prefix}.*",)
        self._publish_timeout = publish_timeout
        self._connect_timeout = connect_timeout
        self._allow_direct = allow_direct
        self._client: Client | None = None
        self._js: JetStreamContext | None = None

    async def start(self) -> None:
        """Connect, and ensure the stream exists.

        Creating the stream is an idempotent API call, unlike a schema
        migration, so it is safe to do on every boot and means a fresh broker
        needs no manual setup step.
        """
        if self._client is not None:
            return
        client = await nats.connect(self._url, connect_timeout=self._connect_timeout)
        js = client.jetstream()
        await self._configure_stream(js)
        # Assigned only once the stream exists, so a failure part-way through
        # leaves the publisher unstarted rather than half-started.
        self._client, self._js = client, js
        logger.info("connected to NATS at {} (stream {})", self._url, self._stream)

    async def stop(self) -> None:
        """Drain the connection so in-flight publishes finish, then close it.

        ``drain()`` closes the connection itself on success, but it *raises*
        when the client is reconnecting or already closed -- and simply dropping
        the reference there would leave the socket open for the life of the
        process. ``close()`` is therefore an unconditional backstop rather than
        an alternative path.

        Shutdown must not raise, so both calls are guarded and the publisher is
        left in a consistent stopped state either way.
        """
        client, self._client, self._js = self._client, None, None
        if client is None:
            return
        try:
            await client.drain()
        except Exception as error:
            logger.warning("NATS did not drain cleanly: {}", error)
        finally:
            if not client.is_closed:
                try:
                    await client.close()
                except Exception as error:
                    logger.warning("NATS did not close cleanly: {}", error)

    def connected(self) -> bool:
        """Whether the broker is usable. Read by the readiness probe."""
        return self._client is not None and self._client.is_connected

    async def publish(self, pointer: dict[str, Any], notification_id: int) -> Any:
        """Publish one change pointer, and wait for the broker to confirm it.

        Waiting for the PubAck is the whole point: it is positive confirmation
        that the message is persisted, so the caller can acknowledge Google
        knowing the work will not evaporate.

        Raises:
            PublishError: if the message was not confirmed, for any reason.
        """
        js = self._js
        if js is None:
            raise PublishError("publisher is not started")

        subject = subject_for(pointer.get("dataType"), self._subject_prefix)
        payload = json.dumps(
            {"notification_id": notification_id, "pointer": pointer}
        ).encode()

        try:
            return await js.publish(subject, payload, timeout=self._publish_timeout)
        except Exception as error:
            # The payload is never logged: a change pointer carries the user's
            # health user id and the interval something happened in.
            raise PublishError(
                f"publish to {subject} was not confirmed: {error}"
            ) from error

    async def _configure_stream(self, js: JetStreamContext) -> None:
        config = StreamConfig(
            name=self._stream,
            subjects=list(self._subjects),
            # File, not in memory: a broker restart must not discard notifications
            # that have not been fetched yet.
            storage=StorageType.FILE,
            # Messages leave the stream when a consumer acknowledges them, which
            # is what makes the stream a work queue rather than a log.
            retention=RetentionPolicy.WORK_QUEUE,
            # Locally only. Paging through a work-queue stream is refused
            # outright without this ("work queue retention streams can only be
            # paged if direct access is allowed"), so browsing the queue while
            # developing needs it. It is a read path and changes nothing about
            # delivery, acking or retention, but it is still a way to read every
            # queued message -- each one naming a user and what they did -- so
            # it is off anywhere that is not a developer's own machine.
            allow_direct=self._allow_direct,
        )
        try:
            await js.update_stream(config=config)
        except NotFoundError:
            await js.add_stream(config=config)
