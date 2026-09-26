# Data model

Part of the [health-cloud design context](CONTEXT.md). What is stored, keyed on
what, and the three rules — idempotency, tombstones, civil time — that keep
reprocessing safe.

Subscribe to **all 29 data types** with the `AUTOMATIC` subscription policy
(Google creates subscriptions on consent; no per-user bookkeeping). Capture
wide, model narrow: display decisions come later, but data not subscribed to
today may be unrecoverable, since subscriptions do not backfill.

Tables:

- `users` — keyed on `healthUserId`, holds encrypted tokens, scopes, consent
  timestamps.
- `raw_notifications` — append-only audit log of every notification received.
  Never used to decide whether to fetch.
- `data_points` — one generic table: `(health_user_id, data_type, record_id,
  start_ts, end_ts, value JSONB, deleted_at, fetched_at)`.

**Settled at step 3:** SQLModel exports generic `JSON` (Postgres `json`) but no
`JSONB`, and `json` can carry neither a GIN index nor a value comparison without
a cast. So `raw_notifications.body` is `JSONB`, through the single
`sqlalchemy.dialects.postgresql` import in the codebase — confined to
`server/models/notification.py` and commented there as the deliberate exception
to the SQLModel-only rule in the [stack](stack.md). `data_points.value` takes the
same type at step 5. No GIN index exists yet; the point of choosing `jsonb` now
is that one can be added later without rewriting the column.

Guessing 25 typed schemas before seeing real payloads is wasted work that would
then need migrating. Promote a type to typed columns or a materialized view only
when its chart gets built.

### Idempotency

Delivery is at-least-once with 7 days of retries, so duplicates are certain.
Dedupe at the **data** level — always fetch, upsert on the natural key, let
reprocessing be a no-op.

Explicitly *not* at the notification level: a duplicate notification and a
genuine correction to the same interval are indistinguishable by payload hash,
so hashing would silently drop real edits. This is why JetStream's `Nats-Msg-Id`
deduplication is left switched off: a broker that offers the trap for free is
still offering the trap.

### Deletions

`operation: DELETE` **tombstones** (`deleted_at`) rather than removing the row.
Reads filter `deleted_at IS NULL`. A deletion that silently rewrites history
would produce unreproducible models once the ML work starts.

### Time

Store all three interval representations. Key the dashboard's daily aggregates
on the **civil (local) date** — "my Tuesday step count" means Tuesday where you
were standing, not Tuesday in UTC. Full-day activities omit
`physicalTimeInterval` entirely. UTC is kept for precise ordering later.

### Fetch strategy

- **Hot path (webhook `UPSERT`):** `GET /v4/users/me/dataTypes/{type}/dataPoints`
  filtered to the notified interval. The notification already says exactly what
  changed, so this is the cheapest correct call.
- **Daily Prefect flow:** `:reconcile` over the trailing 7 days, as the safety
  net that catches what the webhook path missed or deleted.
