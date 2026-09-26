# Stack rationale and conventions

Part of the [health-cloud design context](CONTEXT.md). The stack table itself
lives there; this is why each row was chosen, and the conventions the code
follows as a result.

## Why these

- **NATS JetStream over a Postgres-backed queue.** Settled 2026-09-25. Keeping
  the queue in Postgres was worth a second stateful service only while it bought
  a transactional enqueue alongside the raw-notification insert — and that
  property is **not achievable** with a Postgres queue library here, because the
  psycopg drivers require `autocommit` and so can never share our transaction.
  With atomicity off the table, a real broker earns its keep: durable replay,
  subjects for the fan-out the ML work will want, and a publish acknowledgement
  the receiver can trust. The price is a second stateful service, accepted
  deliberately. Durability then rests on ordering — see
  [Orchestration](orchestration.md).
- **Prefect over Dagster.** Changed 2026-09-25, before any Dagster code existed,
  so the switch cost nothing. The work is a handful of dependent steps over a
  7-day window — fetch, upsert, reconcile — not a partitioned asset graph, and
  the flow/task model states that directly. The deciding factor is the ML work
  under [Deferred](decisions.md#deferred): multi-step pipelines with retries and
  visibility are what Prefect is for, and a message queue has no notion of a
  flow at all. See [Orchestration](orchestration.md) for what Prefect does and
  does not guarantee.
- **No Alembic.** SQLModel is not a migration tool — it creates tables that do
  not exist and cannot alter ones that do. That is acceptable here *only*
  because the backfill window is 7 days: a schema change means wiping the
  database and re-backfilling, which is cheap. **Add Alembic once there is data
  worth preserving** (the ML history is the likely trigger).
- **Plain Postgres.** At one person's volume, TimescaleDB earns nothing yet.
- **Synchronous, SQLModel-only.** SQLModel re-exports `create_engine`,
  `Session`, `select` and `text`, so a sync stack needs essentially no SQLAlchemy
  imports. It exposes no `create_async_engine`, so async would require reaching
  into `sqlalchemy.ext.asyncio`. Sync also fixes the driver as `psycopg`, not
  `asyncpg`. FastAPI runs sync endpoints in a threadpool, which is ample here.
  **One exception exists**, deliberately: `JSONB` is not re-exported, so
  `server/models/notification.py` imports it from
  `sqlalchemy.dialects.postgresql`. It is commented there as the exception, and
  it is the only such import in `server/` — see [Data model](data-model.md). One
  test also imports `sqlalchemy.exc.StatementError`, to construct the database
  failure whose message must never be logged.
- **Tink only where Google requires it.** Google publishes its webhook
  signing keys as a Tink keyset, so Tink verifies those. Using Tink for our
  own secrets would mean cleartext keysets and `secret_key_access.TOKEN`,
  plus a generator command, since a Tink keyset cannot be hand-written.
  `cryptography` and PyJWT take plain hex keys instead.
- **Constants are `Final`, closed sets are `StrEnum`.** Every constant in a
  `const.py` is annotated `Final`, and a constant that is one of a fixed set of
  alternatives is an enum instead: `LogPolicy`, `SubscriptionPolicy`,
  `SubscriberState`. `StrEnum` specifically, so members still compare equal to
  the strings Google sends and still serialise as plain strings in JSON. The
  payoff is that invalid values stop being writable — the CLI derives its
  `--policy` choices from `SubscriptionPolicy` rather than repeating them, and
  `log_policy` no longer needs a hand-written membership check. Enforced by
  **mypy, which runs in CI** ahead of the tests, with the pydantic plugin so
  `Settings()` and the SQLModel tables type-check, and missing-import ignores
  named for the only two dependencies that ship no types (`tink`,
  `google_auth_oauthlib`) rather than applied globally.
- **Open sets stay tuples.** `DATA_TYPES` is deliberately *not* an enum. Google
  can add a data type at any time, and an enum would turn an unrecognised one
  into a crash on a live notification; the receiver routes unknown types to a
  subject of their own instead. The same reasoning keeps `ENVIRONMENT` a plain
  string.
- **Helpers live in each module's `util.py`.** Pure helpers move out of the
  module they serve, so a file's main abstraction is what a reader meets first.
  A function is never left in `const.py`.
- **Classes over module-level functions.** Collaborators take configuration
  through `__init__` and never read settings themselves, so they are
  constructible in tests without an environment. `server/providers.py` is
  the single wiring point, and its `lru_cache` factories are the only
  shared instances. Constants live in each module's `const.py`.
- **`requests` for outbound HTTP.** `httpx2` remains a dev-only dependency
  because Starlette's `TestClient` is built on it; it is not used for our own
  calls.
- **Imports are absolute from the project root** (`server.module.submodule`).
  No relative imports.
- **Settings carry no defaults.** Every field is required, so a missing variable
  fails at import with a `ValidationError` naming it. Variables for later steps
  are added by those steps.
