"""The ``raw_notifications`` table.

An append-only record of every webhook delivery that verified as Google's. It is
never consulted to decide whether to fetch -- delivery is at-least-once and a
duplicate is indistinguishable from a genuine correction, so the decision to
fetch is always yes and dedupe happens at the data level.
"""

from datetime import datetime
from typing import Any

from sqlmodel import Column, Field, SQLModel

from server.models.encrypted import EncryptedJSON
from server.models.util import utc_column


class RawNotification(SQLModel, table=True):
    __tablename__ = "raw_notifications"

    id: int | None = Field(default=None, primary_key=True)

    received_at: datetime = Field(sa_column=utc_column(nullable=False))

    #: The X-Request-ID the middleware assigned, so a row and the request's log
    #: line can be put side by side. Nullable because a notification handled
    #: without the middleware mounted is still worth recording.
    request_id: str | None = Field(default=None, index=True)

    #: The delivery as Google sent it, parsed and encrypted. Parsed rather than
    #: the original bytes, so the signature cannot be re-verified from the
    #: database, which nothing does.
    body: Any = Field(sa_column=Column(EncryptedJSON(), nullable=False))

    #: How many change pointers the delivery carried. Google batches, so this is
    #: routinely more than one, and it makes "did we publish everything?"
    #: answerable without unpacking the body.
    pointer_count: int
