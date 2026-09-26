"""Stand-ins for the database and the broker, for tests about the route's logic.

These exist to make the *ordering* checkable without infrastructure: both
doubles write to one shared journal, so a test can assert that the audit row
committed before anything was published. They deliberately cannot prove the
durability guarantees themselves -- a fake cannot roll back a transaction it is
not in, and cannot persist a message. Those live in tests/integration/.
"""

import threading
from typing import Any

from server.queue.error import PublishError


class Journal(list):
    """What happened, in the order it happened."""

    def steps(self) -> list[str]:
        return [step for step, _ in self]


class FakeSession:
    """Records what the route did, and fails on demand."""

    def __init__(self, journal: Journal, fail: bool = False) -> None:
        self.journal = journal
        self.fail = fail
        self.added: list[Any] = []
        self.rolled_back = False
        #: Which thread committed. The route offloads the blocking write, so
        #: this must not be the thread running the event loop.
        self.commit_thread: int | None = None

    def add(self, instance: Any) -> None:
        self.added.append(instance)

    def commit(self) -> None:
        if self.fail:
            raise RuntimeError("database is down")
        self.commit_thread = threading.get_ident()
        self.journal.append(("commit", len(self.added)))

    def refresh(self, instance: Any) -> None:
        # The real session populates the generated primary key here, and the
        # route puts that id into every message it publishes.
        if getattr(instance, "id", None) is None:
            instance.id = 1

    def rollback(self) -> None:
        self.rolled_back = True

    def exec(self, *_args: Any, **_kwargs: Any) -> Any:
        if self.fail:
            raise RuntimeError("database is down")
        return None


class FakePublisher:
    """Records published messages, and fails on demand."""

    def __init__(self, journal: Journal, fail: bool = False) -> None:
        self.journal = journal
        self.fail = fail
        self.published: list[tuple[int, dict]] = []
        #: Which thread published. Awaited directly, so this is the loop's.
        self.publish_thread: int | None = None

    async def publish(self, pointer: dict, notification_id: int) -> object:
        if self.fail:
            raise PublishError("broker is unreachable")
        self.publish_thread = threading.get_ident()
        self.published.append((notification_id, pointer))
        self.journal.append(("publish", pointer.get("dataType")))
        return object()

    def connected(self) -> bool:
        return not self.fail
