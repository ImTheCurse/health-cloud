"""The ``raw_notifications`` table.

An append-only record of every webhook delivery that verified as Google's. It is
never consulted to decide whether to fetch -- delivery is at-least-once and a
duplicate is indistinguishable from a genuine correction, so the decision to
fetch is always yes and dedupe happens at the data level.
"""

from datetime import datetime
from typing import Any

# The one place the project reaches past SQLModel into SQLAlchemy. SQLModel
# re-exports generic `JSON` (Postgres `json`) but no `JSONB`, and `json` cannot
# carry a GIN index or compare values without a cast. Everything else in the
# codebase stays SQLModel-only.
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Column, Field, SQLModel

from server.models.util import utc_column


class RawNotification(SQLModel, table=True):
    __tablename__ = "raw_notifications"

    id: int | None = Field(default=None, primary_key=True)

    received_at: datetime = Field(sa_column=utc_column(nullable=False))

    #: The X-Request-ID the middleware assigned, so a row and the request's log
    #: line can be put side by side. Nullable because a notification handled
    #: without the middleware mounted is still worth recording.
    request_id: str | None = Field(default=None, index=True)

    #: The delivery exactly as Google sent it, parsed. Stored as jsonb rather
    #: than the original bytes: queryable, at the cost of no longer being able
    #: to re-verify the signature from the database, which nothing does.
    body: Any = Field(sa_column=Column(JSONB, nullable=False))

    #: How many change pointers the delivery carried. Google batches, so this is
    #: routinely more than one, and it makes "did we publish everything?"
    #: answerable without unpacking the body.
    pointer_count: int
