"""A fake JetStream pull subscription.

The consumer's contract is about *when* it acknowledges, and that is visible from
the message objects alone -- a real broker is not needed to see that ack came
after the handler returned, or that it never came at all. Whether the broker then
redelivers is a property of JetStream, and that lives in tests/integration/.
"""

import json
from typing import Any

from nats.errors import TimeoutError as NatsTimeoutError


class FakeMessage:
    """Records what was done to it, in order."""

    def __init__(self, payload: Any, journal: list, raw: bytes | None = None) -> None:
        self.data = raw if raw is not None else json.dumps(payload).encode()
        self.journal = journal
        self.acked = False
        self.termed = False

    async def ack(self) -> None:
        self.acked = True
        self.journal.append("ack")

    async def term(self) -> None:
        self.termed = True
        self.journal.append("term")


class FakeSubscription:
    """Hands out prepared batches, then behaves like an empty stream.

    An empty pull raises ``TimeoutError`` in ``nats-py``, which is how a drain
    discovers it is finished, so the fake has to do the same -- returning an empty
    list instead would let the consumer pass a test it would fail against NATS.
    """

    def __init__(self, batches: list[list[FakeMessage]]) -> None:
        self._batches = list(batches)
        self.fetches = 0

    async def fetch(self, batch: int, timeout: float) -> list[FakeMessage]:
        self.fetches += 1
        if not self._batches:
            raise NatsTimeoutError
        return self._batches.pop(0)
