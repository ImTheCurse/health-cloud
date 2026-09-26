# health-cloud — design context

Agreed 2026-09-22. This records *what was decided and why*, so the reasoning
survives past the conversation that produced it.

## What it is

A self-hosted personal pipeline that ingests Google Health data from compatible
devices (Fitbit trackers, Pixel Watch, other Google Health app devices), stores
it in Postgres, and displays it in a React dashboard.

Single user. Runs locally during development, then on an existing self-hosted
server.

## The central mechanic

**The webhook does not deliver health data.** It delivers change pointers, as
a JSON **array of envelopes**, each wrapping one pointer under `data`:

```json
[
  {
    "data": {
      "version": "1",
      "clientProvidedSubscriptionName": "auto-<project>-<subscriber>-WEBHOOK_DATA_TYPE_SLEEP",
      "healthUserId": "...",
      "operation": "UPSERT | DELETE",
      "dataType": "sleep",
      "intervals": [ { "physicalTimeInterval": {...},
                       "civilDateTimeInterval": {...},
                       "civilIso8601TimeInterval": {...} } ],
      "recordId": "..."
    }
  }
]
```

> **Verified against live traffic, 2026-09-24.** The array-of-envelopes shape is
> not what the documentation's example suggests, and getting it wrong is not
> cheap: a parser written against a bare object refused every real notification
> with `403`, and because the refusal shared an exception type with signature
> failure it looked like a crypto problem. One delivery can carry **several**
> pointers, so a parser that reads only the first silently loses data. A bare
> object is still accepted, since the docs show one.

The notification says *that* steps changed for a user over an interval, never
what the step count is. The server must then query the Health API with that
user's access token to read the values. This is the API's design, not a
configuration we can change, and it is why a fetcher worker is mandatory rather
than an architectural preference.

Flow:

```
Google Health  --webhook-->  receiver  -->  NATS       -->  Prefect flow
                             (verify sig,      JetStream    (pull, refresh token,
                              audit row,       (file)        list dataPoints,
                              publish, 204)                  upsert, then ack)
                                                                 |
                                                                 v
                                                             Postgres
                                                                 |
                                                     FastAPI read API
                                                                 |
                                                        React dashboard
```

The receiver is deliberately dumb and fast: verify, record, publish,
acknowledge, nothing else. All fragile work (token refresh, pagination, rate limits) lives in
workers, where retries are free.

## Stack

| Concern | Choice |
| --- | --- |
| Language | Python 3.13 (backend), JavaScript (frontend — not TypeScript) |
| Web framework | FastAPI |
| ORM / models | SQLModel only — no direct SQLAlchemy imports |
| Migrations | **None.** `SQLModel.metadata.create_all()` only |
| Database | Postgres, plain (no TimescaleDB) |
| DB driver | `psycopg` (sync) |
| Concurrency | Synchronous — SQLModel has no async engine |
| Outbound HTTP | `requests` |
| OAuth flow | `google-auth-oauthlib` |
| Crypto | `cryptography` AES-256-GCM for tokens at rest; PyJWT HS256 for session cookies; Tink **only** for Google's webhook signature keyset (step 3) |
| Message queue | NATS JetStream, file storage, consumed by Prefect |
| Orchestration | Prefect 3, self-hosted |
| Flow code | `server/flows/`, `prefect` in its own dependency group |
| Frontend | React |
| Layout | Monorepo: `server/` + `client/`, separate deploy artifacts |
| Config | `.env` |
| Tests | pytest |

### Why these

- **NATS JetStream over a Postgres-backed queue.** Settled 2026-09-25. Keeping
  the queue in Postgres was worth a second stateful service only while it bought
  a transactional enqueue alongside the raw-notification insert — and that
  property is **not achievable** with a Postgres queue library here, because the
  psycopg drivers require `autocommit` and so can never share our transaction.
  With atomicity off the table, a real broker earns its keep: durable replay,
  subjects for the fan-out the ML work will want, and a publish acknowledgement
  the receiver can trust. The price is a second stateful service, accepted
  deliberately. Durability then rests on ordering — see *Orchestration*.
- **Prefect over Dagster.** Changed 2026-09-25, before any Dagster code existed,
  so the switch cost nothing. The work is a handful of dependent steps over a
  7-day window — fetch, upsert, reconcile — not a partitioned asset graph, and
  the flow/task model states that directly. The deciding factor is the ML work in
  *Deferred*: multi-step pipelines with retries and visibility are what Prefect
  is for, and a message queue has no notion of a flow at all. See *Orchestration* for
  what Prefect does and does not guarantee.
- **No Alembic.** SQLModel is not a migration tool — it creates tables that do
  not exist and cannot alter ones that do. That is acceptable here *only*
  because the backfill window is 7 days: a schema change means wiping the
  database and re-backfilling, which is cheap. **Add Alembic once there is data
  worth preserving** (the ML history is the likely trigger).
- **Plain Postgres.** At one person's volume, TimescaleDB earns nothing yet.
- **Synchronous, SQLModel-only.** SQLModel re-exports `create_engine`,
  `Session`, `select` and `text`, so a sync stack needs no SQLAlchemy imports at
  all. It exposes no `create_async_engine`, so async would require reaching into
  `sqlalchemy.ext.asyncio`. Sync also fixes the driver as `psycopg`, not
  `asyncpg`. FastAPI runs sync endpoints in a threadpool, which is ample here.
- **Tink only where Google requires it.** Google publishes its webhook
  signing keys as a Tink keyset, so Tink verifies those. Using Tink for our
  own secrets would mean cleartext keysets and `secret_key_access.TOKEN`,
  plus a generator command, since a Tink keyset cannot be hand-written.
  `cryptography` and PyJWT take plain hex keys instead.
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

## Authentication

Google-only. One flow covers both signing in to the web UI and granting Health
consent. There is no password registration — which removes password storage,
resets, and credential stuffing from the threat model entirely.

- **Scopes:** read-only, all 9, plus `openid` / `email` / `profile` for the
  session's identity (non-restricted, same single consent screen) (`activity_and_fitness`, `ecg`,
  `health_metrics_and_measurements`, `irn`, `location`, `nutrition`, `profile`,
  `settings`, `sleep`). No write scopes: nothing writes back to Google.
- **Session:** self-signed short-lived JWT (30–60 min) in an
  `httpOnly; Secure; SameSite=Lax` cookie, renewed server-side. Never
  `localStorage` — that is the XSS exposure this design is avoiding. Google's ID
  token is *not* a session (≈1 hour, unextendable without bouncing through
  Google), so minting our own credential is unavoidable.
- **CSRF:** double-submit token on state-changing requests. Cookie auth needs
  this regardless of JWT vs opaque sessions.
- **Refresh token:** stays server-side, encrypted at rest. Never reaches the
  browser.
- **Client credentials:** `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` in `.env`.
  They identify the *app*, not a user, so they are config — not something a UI
  form accepts and stores.
- **CORS:** the API lists allowed origins explicitly (`CORS_ORIGINS`) with
  `allow_credentials=True`; a wildcard is rejected by browsers in that mode.
- **Cookie domain:** client and API must share a registrable domain
  (e.g. `app.<domain>` + `api.<domain>`) for cookie auth to work across the two
  deployments.

## The defining constraint: 7-day token expiry

Google Health scopes are **restricted**. Verification requires a third-party
CASA security assessment costing $500–$4,500 and taking 2–6 weeks — not
justifiable for a single user.

So the OAuth client **stays in `Testing` publishing status forever**, and
testing-mode refresh tokens expire after 7 days, failing with `invalid_grant`.

Mitigation — one-click re-consent, plus alerting driven by three signals:

1. `invalid_grant` on a refresh attempt (reactive)
2. A proactive countdown from token issue time
3. `user-revoked-access` / `user-deleted` webhook events

Alerts go to **push** (ntfy/Gotify), not just a UI banner. A UI-only warning
fails exactly when it is needed: you stop opening a dashboard that has no fresh
data, so the one place the warning appears is the place you have stopped
visiting.

### A useful convergence

Three independent 7-day windows line up:

- Google retries undelivered notifications for 7 days
- Testing-mode refresh tokens live 7 days
- The chosen backfill window is 7 days

So a single recurring Prefect flow — *"reconcile the last 7 days for every data
type"* — covers first-connect backfill, post-re-consent gap recovery, and
anything the webhook dropped.

## Data model

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
  start_ts, end_ts, value JSON, deleted_at, fetched_at)`.

**Open at step 5:** SQLModel exports generic `JSON` (Postgres `json`) but no
`JSONB`. A GIN index needs `jsonb`, which means either one
`sqlalchemy.dialects.postgresql` import or accepting `json` without the index.

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

## Orchestration

Prefect 3, self-hosted. Settled 2026-09-25.

**What Prefect guarantees, and what it does not.** Prefect is *not* replay-based
durable execution. What it offers is transactions with at-most-once semantics via
a computed cache key, task result caching, and retries. Two defaults matter:
result persistence is **off** by default and lands in `~/.prefect/storage/`, and
the default cache key includes the **flow run id**, so cached results are reused
across retries of one run, not across a fresh run. Cross-run resumption needs a
deliberate `cache_key_fn` or transaction key.

That is accepted rather than worked around, because the unit of work — *fetch one
data type over one interval and upsert on the natural key* — is already
idempotent. Re-executing it costs an HTTP call, not correctness, so replay buys
little. A transaction key per `(health_user_id, data_type, interval)` makes a
rerun cheap; that is as far as it needs to go. If genuine resume-from-last-step
is ever needed, that is the point to revisit Temporal.

**The path a notification takes.** The receiver records the delivery, publishes
one message per change pointer to NATS JetStream, and only then answers 204. A
Prefect flow pulls those messages, does the work, and acknowledges each one.

The receiver half is built (step 3). The flow, and the optional trigger that
starts one promptly rather than waiting for its schedule, arrive with step 5 —
until then messages accumulate in the stream, which is exactly what a durable
work queue is for.

**NATS JetStream, not core NATS.** Core NATS is at-most-once and never replays:
a message published while no subscriber is connected is simply gone. Durability
means JetStream — a stream with **file** storage on a named volume, plus per
message acknowledgements. Memory-backed streams were rejected: a
`docker compose restart` would silently discard every un-fetched notification.
The stream sets `allow_direct` **only when `ENVIRONMENT` is `local`**: without
it a work-queue stream refuses to be paged at all, so browsing the queue while
developing needs it, but it also permits reading every queued message — each one
naming a user and what they did — so it stays off everywhere else.

**Ordering carries what atomicity cannot.** No external broker can join a
Postgres transaction, so the sequence is fixed and the ordering does the work:

1. insert the `raw_notifications` row and **commit**
2. publish one message per pointer, and **wait for the JetStream `PubAck`**
3. only then answer **204**

Any failure answers **503** instead, and Google's 7-day redelivery is the retry.
Nothing is lost. The residue of a failure is a *duplicate* audit row on
redelivery, which is harmless: the log is append-only and dedupe lives at the
data level. The audit row commits first deliberately — the reverse order could
leave work running with no record of what asked for it. Message payloads are
self-contained, so a flow never reads the audit table to do its work.

The `PubAck` matters: it is positive confirmation from the server that the
message is persisted, so the 204 is never sent on the strength of a fire and
forget publish.

**The client is asyncio-only.** `nats-py` has no synchronous client — `connect`
and `publish` are both coroutines, and nothing in the package offers a blocking
form. Since the receiver is deliberately synchronous, the connection lives on a
dedicated event-loop thread opened at startup, and the route publishes with
`asyncio.run_coroutine_threadsafe(...).result(timeout=...)`. One warm connection,
no per-request handshake, and no event loop inside a sync route.

**The flow is a pull consumer.** There is no `prefect-nats` integration; it does
not exist on PyPI. The flow fetches a batch from a durable JetStream consumer and
acknowledges each message **only after its upsert has committed**, which is what
makes at-least-once mean something. A bridge process that subscribed and called
`run_deployment` per message was rejected: it acknowledges before the work is
durable, so a failed flow loses the message, and it adds a third process with a
second state machine.

**JetStream's own deduplication is deliberately unused.** A `Nats-Msg-Id` within
the stream's duplicate window would collapse repeat deliveries, which is the same
trap as a queue-level dedupe key: a duplicate delivery and a genuine correction
to the same interval are indistinguishable. Dedupe stays at the data level — see
*Idempotency*.

**The stream is created by the app, not by a setup command.** Creating a
JetStream stream is an idempotent API call rather than a schema migration, so
`publisher.start()` does it on every boot and a fresh broker needs no manual
step. The NATS CLI is useful for looking at the queue but is **not** required to
run the app or the tests -- see the README.

**Deployment shape.** Prefect's server, its background `prefect server services`
process, its worker and its **own** Postgres container all run under
`docker-compose.yml`, deliberately separate from the app's Postgres: Prefect runs
Alembic migrations over its schema, and this project's stack table says
*Migrations: None*. Letting another tool's migrations into the app's database
would end the ability to reason about it. The FastAPI app itself is still run by
hand; containerising it belongs to step 8.

**Flow code lives in `server/flows/`.** The flows need `server.models`,
`server.db` and `server.crypto`, so they share the package. The import direction
is one-way — flows may import `server`, never the reverse. `prefect` is declared
in its own dependency group, not as an API dependency, because it pulls roughly
50 extra packages (including `alembic`, `asyncpg` and `docker`) that the web
process never imports.

**A database error's message is not safe to log.** A SQLAlchemy
`StatementError` stringifies with its statement *and bound parameters*
attached, and for the receiver those parameters are the delivery's health data.
Failure paths therefore log `type(error).__name__`, never `str(error)`. Found by
checking rather than by leaking, 2026-09-25, and covered by a test.

**Not available self-hosted:** Prefect's HTTP *webhooks*, which turn an external
request into a Prefect event, are a Cloud feature. Events and automations are in
the open-source server; the webhook receiver is not. Nothing in this design needs
it — Google talks to our own endpoint — but it is worth not rediscovering.

## Webhook endpoint requirements

- Public HTTPS, TLSv1.2+.
- **Two-step verification handshake** on subscriber create/update:
  - authorized `POST {"type":"verification"}` → must return **200 or 201**
  - *unauthorized* `POST` (same body, no credentials) → must return **401 or 403**
  - failing either → `FAILED_PRECONDITION`, with no useful detail
- **Signature:** ECDSA P-256 / SHA-256, Base64 in the `GOOGLE-HEALTH-API-SIGNATURE`
  header, verified against Tink's public keyset at
  `https://www.gstatic.com/googlehealthapi/webhooks/webhooks_public_keyset.json`
  (rotated every 30 days — fetch and cache, never pin).
- **Acknowledge with `204 No Content` immediately.** Anything else triggers
  retry with exponential backoff for up to 7 days.
- **Match the handshake body exactly**, i.e. `body == {"type": "verification"}`.
  Accepting any body that merely *contains* that key lets a caller holding the
  shared secret attach the marker to a change pointer and skip signature
  verification entirely — the secret alone must never be sufficient. Found by
  security review, 2026-09-24.
- **Keep "bad signature" and "unreadable body" as distinct failures.** Both
  answer `403`, but a body Google signed that we cannot parse means *our*
  parser is wrong, and it must say so loudly. Collapsing them into one silent
  refusal is what hid the payload-shape bug above.

## Rate limits

300 requests/minute per user; effectively ~2.5 QPS for an unverified app.
Throttling returns `429`. Backfill must be paced accordingly.

## Operations

- **The subscriber resource has no `state` field.** The discovery document
  describes an `UNVERIFIED`/`ACTIVE`/`INACTIVE` enum; the live API does not
  return one, and there is no `get` method either — only `list`. Treating a
  missing state as a failure made a successful registration print as broken.
  The real confirmation is that `create` returned at all: a failed handshake
  fails the call with `FAILED_PRECONDITION` rather than registering something
  unverified.
- **Subscriber lifecycle via CLI** (`create` / `update` / `delete`), never at app
  startup. Startup reconciliation risks a restart silently repointing or failing
  the handshake on the production subscriber; the cutover should be a deliberate
  act with visible output.
- **Local:** ngrok with a **static domain** (free tier includes one). Without it,
  every tunnel restart is a new URL, meaning a subscriber update and
  re-verification each session.
- **Production:** cloudflared on the self-hosted server. Cutover is one
  subscriber PATCH plus one handshake.
- **Ops surfaces:** Prefect's own UI for fetch failures, push notifications for
  token expiry. No separate status page — it would be redundant.

## Observability

**loguru**, configured once in `server/config/logging.py`. Human-readable and
colourised when `ENVIRONMENT=local`, structured JSON everywhere else — the same
fields either way, so a line read in a terminal is the line an aggregator would
parse. `diagnose=False` on the JSON sink is deliberate: loguru's diagnostic
tracebacks inline local variable values, which on these paths would put
notification bodies and decrypted tokens in the log.

**One aggregated record per request**, not a line per thing that happened. The
middleware (`@app.middleware("http")`, per FastAPI's documented form) builds a
`RequestLog` and emits it once in a `finally`, so a request that raised still
produces a line carrying `message` and `cause`:

```
request_id, method, path, status, duration_ms, is_secure,
x_forwarded_for, user, events[], error{message, cause}
```

Anything in the request adds to it with `add_event(request, name, **fields)`.
The record lives on **`request.state`** and every accessor takes the request
explicitly — nothing ambient, and two requests in flight hold unrelated
objects. A concurrency test asserts that directly, and was confirmed to fail
when isolation is deliberately broken.

`request_id` is generated per request and echoed as `X-Request-ID`. An inbound
one is **ignored**: this endpoint is internet-facing, and trusting a caller's
id would let them forge or collide correlation.

`user` is a six-hex-character SHA-256 truncation of `healthUserId`, computed on
demand and **not stored** — it is a pure function, so it can always be
recomputed to identify which user a line refers to. A raw health user id,
combined with a data type and a timestamp, *is* a health record.

**Never logged, unconditionally:** request and response bodies, `Authorization`,
cookies, and the signature header.

**Log level is a per-route policy, not sampling.** Nothing is discarded and
nothing is decided by chance; the policy only chooses a level, and a `DEBUG`
record is still there for anyone who lowers the threshold. The default is
`ALWAYS`, so a new route is logged in full from the day it is written and going
quiet is a visible decision in the source:

```python
@router.get("/healthz")
@log_policy(QUIET)
def healthz() -> dict[str, str]: ...
```

A `QUIET` route drops routine successes to `DEBUG` but still speaks up on
`status >= 400`, an exception, or any domain event. Only `/healthz` and
`/readyz` are quiet today. Locally everything is `INFO` regardless.

uvicorn's own loggers are left alone, so each request currently produces **two**
lines — uvicorn's access line and ours. Collapsing them is a small
`InterceptHandler` change if the duplication becomes annoying.

## Testing

pytest, with priority on the two places where a bug means Google silently
refuses to talk to the service at all:

1. Signature verification (using a locally generated test keyset)
2. The 200/401 verification handshake

Plus replayed notification fixtures and idempotent-upsert tests. These land
**before** a real subscriber is registered — a handshake bug is miserable to
debug live.

**Test behaviour, not logging.** Assert the exception a function raises and the
status a route returns; do not assert that a function logged. The exception is
what the rest of the system reacts to, and a test that pins log wording breaks
on every rewording while protecting nothing. The deliberate exception is a
small set asserting that sensitive values — notification bodies, the shared
secret, the signature, the raw health user id — **never reach a log**, which is
a security property rather than a message format.

**Fixtures must match what Google really sends.** The payload-shape bug above
survived a green suite because the fixture was the shape we imagined. Test
doubles are built from captured live traffic, with every real identifier
replaced by an invented one of the same form (`FAKE_HEALTH_USER_ID`,
`FAKE_PROJECT_NUMBER`, `FAKE_RECORD_ID` in `tests/google_webhook.py`) so no
account, record or sleep time reaches the repository.

**A test that cannot fail is not a test.** Leakage assertions first check that
something *was* logged, or they pass vacuously; a tamper-detection test checks
that the body it altered actually differs. Both guards were added after the
real versions silently stopped testing anything.

## Build order

Progress marker — tick a box only when the step is genuinely complete.
**Each step requires explicit confirmation before implementation.**

- [x] **1. Project skeleton** — monorepo `server/` + `client/`, docker-compose
      Postgres, `.env` scaffold, add `.env` to `.gitignore`
- [x] **2. Google OAuth end to end** — consent flow, encrypted token storage,
      JWT cookie session, one-click re-consent
- [x] **3. Webhook receiver** — signature verification, 200/401 handshake,
      audit row, publish to NATS JetStream, 204 ack, **with pytest coverage**
      — *done 2026-09-25.* `raw_notifications` holds one row per delivery with
      the payload as `jsonb`; one message per change pointer goes to
      `health.notifications.<dataType>` on a file-backed work-queue stream, and
      the 204 waits on both. Verified end to end against a booted app: a batched
      delivery produced one audit row with `pointer_count: 2` and two messages in
      the stream. Readiness reports both dependencies. 143 tests, including
      integration tests against real Postgres and real NATS in CI.
- [x] **4. Subscriber CLI + ngrok static domain** — register a real subscriber,
      confirm live notifications land
      — *done 2026-09-24.* The subscriber named in `SUBSCRIBER_ID` was
      registered on the project in `GCP_PROJECT_NUMBER` against an ngrok static
      domain; Google's handshake was observed passing from its own IPs (401 then
      200), and real `sleep` / `distance` notifications acknowledged with 204.
      Identifiers live in `.env`, never here.
- [ ] **5. Fetcher flow** — a Prefect flow that pulls from JetStream, refreshes
      the token, `list`s the notified interval, upserts idempotently and **then**
      acknowledges, **plus one-off backfill CLI**
- [ ] **6. React dashboard** — steps, sleep, heart rate
- [ ] **7. Prefect schedule** — daily 7-day `:reconcile` flow + push alerting
      on token expiry
- [ ] **8. Cutover to cloudflared** — subscriber PATCH to the self-hosted URL

Step 3 precedes step 4 deliberately: verification logic is tested against
fixtures before Google is ever pointed at the endpoint.

**That ordering was deviated from**, by choice, on 2026-09-24: step 4 was done
against a log-only receiver so that real deliveries could be seen before
persistence was built. It was the right call for an unrelated reason — real
traffic immediately exposed the payload-shape error that fixtures had not.
Persistence landed the following day, within Google's 7-day retry window, so
nothing delivered in between was lost.

The dashboard precedes the recurring schedule by choice; the backfill CLI in
step 5 exists so the dashboard has real data to draw before it is built.

## Open decisions

Deliberately unresolved — decide these at the step that needs them, with the
user, rather than assuming.

| Decision | Needed by | Notes |
| --- | --- | --- |
| ~~Token encryption library~~ | ~~Step 2~~ | **Settled: not Tink.** `cryptography` AES-256-GCM (`TOKEN_ENCRYPTION_KEY`) and PyJWT HS256 (`SESSION_SECRET`), both plain `openssl rand -hex 32` values. Tink is reserved for verifying Google's published webhook keyset, which needs no secret key material |
| Push alert service | Step 7 | ntfy vs Gotify — likely whichever is already running on the self-hosted box |
| How `client/` is served in production | Step 6 / 8 | Tooling settled at step 1: **Vite + React (JavaScript)**. Still open: static build served from the same host as the API, sharing a registrable domain for cookie auth |
| ~~Role of `google-credentials.json`~~ | ~~Step 2~~ | **Settled: none.** Client ID/secret live in `.env`; the file is kept but unused |
| ~~Logging~~ | ~~Step 3~~ | **Settled: loguru**, one aggregated record per request on `request.state`, per-route level policy defaulting to full. See *Observability* |
| ~~Storing a log-safe user handle~~ | ~~Step 3~~ | **Settled: not stored.** A truncated SHA-256 of `healthUserId` is a pure function, so it is recomputed on demand — no column, no migration |
| ~~Orchestrator~~ | ~~Step 7~~ | **Settled 2026-09-25: Prefect**, self-hosted. See *Orchestration* |
| Stream and consumer configuration | Step 3 | Stream name, subject scheme, retention policy, `max_age`, and the consumer's `ack_wait` and `max_deliver`. Defaults chosen at implementation, to be revisited once real volume is visible |
| NATS authentication | Step 3 | None on the compose network initially, with the port bound to localhost. Revisit at step 8, when the box is reachable from outside |
| ~~Queue technology~~ | ~~Step 3~~ | **Settled 2026-09-25: NATS JetStream**, file storage. See *Orchestration* and *Why these* |
| ~~How durability is guaranteed~~ | ~~Step 3~~ | **Settled: ordering, not atomicity.** No broker can join our transaction; commit → publish → `PubAck` → 204, and 503 otherwise, loses nothing given Google's 7-day retry |
| What a failed flow trigger means | Step 5 | Whether a failed `run_deployment` is swallowed because the queue is the source of truth, and whether the deployment also carries an interval schedule as a sweep |
| ~~Postgres in CI~~ | ~~Step 3~~ | **Settled 2026-09-25: yes.** A `postgres:17-alpine` service plus `pgq install` on the `backend-api` job. Declined earlier only while nothing touched a database |

## Deferred

- Chart selection beyond steps / sleep / heart rate
- The ML layer over collected data — `raw_notifications` and the JSONB
  `data_points` already preserve what it will need

## Rejected alternatives

| Rejected | Why |
| --- | --- |
| Apache Kafka, Apache Airflow | Ruled out by the user |
| Temporal | Genuine replay-based durable execution, but the unit of work here is already idempotent, so replay earns little against its footprint. Reconsidered and re-rejected 2026-09-25 |
| Dagster | Chosen at design time, dropped 2026-09-25 before any code existed — assets and partitions model more structure than one 7-day reconcile needs |
| Prefect as the queue as well | `run_deployment` is fire-and-forget over HTTP with no persistence or acknowledgement of its own, so a lost call is lost work |
| RabbitMQ | Rejected as a second stateful service — an objection since withdrawn: NATS is that second service, accepted deliberately 2026-09-25 |
| pgqueuer | Tried 2026-09-25 and dropped. Its psycopg drivers require `autocommit`, so the transactional enqueue that justified it is impossible; no synchronous consumer; `dequeue` leaves the job state machine to the caller |
| Core NATS without JetStream | At-most-once with no replay — a message published with no subscriber connected is gone |
| Memory-backed JetStream storage | A container restart would discard every un-fetched notification |
| TimescaleDB | Earns nothing at single-user volume |
| Fitbit Web API | Superseded by the Google Health API for new projects |
| CASA verification | $500–$4,500 for one user |
| Password auth alongside Google | Doubles auth attack surface, secures nothing extra |
| Opaque session IDs | JWT preferred; revocation is near-worthless at one user |
| 25 typed tables | Premature; display types undecided |
| Notification-level dedupe | Cannot distinguish duplicates from genuine corrections |
| Separate status page | Prefect UI + push alerts already cover it |

## References

- [Google Health API setup](https://developers.google.com/health/setup)
- [Webhook subscriptions](https://developers.google.com/health/webhooks)
- [projects.subscribers](https://developers.google.com/health/reference/rest/v4/projects.subscribers)
- [Data management](https://developers.google.com/health/data-management)
- [OAuth scopes](https://developers.google.com/health/scopes)
- [App verification](https://developers.google.com/health/app-verification)
- [Rate limits](https://developers.google.com/health/rate-limits)
