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

**The webhook does not deliver health data.** It delivers a change pointer:

```json
{
  "version": "1",
  "clientProvidedSubscriptionName": "...",
  "healthUserId": "...",
  "operation": "UPSERT | DELETE",
  "dataType": "steps",
  "intervals": [ { "physicalTimeInterval": {...},
                   "civilDateTimeInterval": {...},
                   "civilIso8601TimeInterval": {...} } ],
  "recordId": "..."
}
```

The notification says *that* steps changed for a user over an interval, never
what the step count is. The server must then query the Health API with that
user's access token to read the values. This is the API's design, not a
configuration we can change, and it is why a fetcher worker is mandatory rather
than an architectural preference.

Flow:

```
Google Health  --webhook-->  receiver  -->  pgqueuer  -->  fetcher worker
                             (verify sig,                  (refresh token,
                              204, enqueue)                 list dataPoints,
                                                            upsert)
                                                                 |
                                                                 v
                                                             Postgres
                                                                 |
                                                     FastAPI read API
                                                                 |
                                                        React dashboard
```

The receiver is deliberately dumb and fast: verify, acknowledge, enqueue,
nothing else. All fragile work (token refresh, pagination, rate limits) lives in
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
| Queue | pgqueuer (Postgres-backed) |
| Orchestration | Dagster |
| Frontend | React |
| Layout | Monorepo: `server/` + `client/`, separate deploy artifacts |
| Config | `.env` |
| Tests | pytest |

### Why these

- **pgqueuer over RabbitMQ.** Postgres is already running, so enqueue is
  transactional with the raw-notification insert — which removes an entire class
  of lost-or-duplicated-across-two-systems bugs. RabbitMQ would be a second
  stateful service to operate for one person's step counts.
- **Dagster over Prefect/Temporal.** Temporal is durable execution, not a DAG
  engine, and self-hosting means running its own server and datastore. Dagster's
  partitioned assets and one-command local UI (`dagster dev`) fit the recurring
  catch-up job directly.
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

So a single recurring Dagster job — *"reconcile the last 7 days for every data
type"* — covers first-connect backfill, post-re-consent gap recovery, and
anything the webhook dropped.

## Data model

Subscribe to **all 25 data types** with the `AUTOMATIC` subscription policy
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
so hashing would silently drop real edits.

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
- **Daily Dagster job:** `:reconcile` over the trailing 7 days, as the safety
  net that catches what the webhook path missed or deleted.

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

## Rate limits

300 requests/minute per user; effectively ~2.5 QPS for an unverified app.
Throttling returns `429`. Backfill must be paced accordingly.

## Operations

- **Subscriber lifecycle via CLI** (`create` / `update` / `delete`), never at app
  startup. Startup reconciliation risks a restart silently repointing or failing
  the handshake on the production subscriber; the cutover should be a deliberate
  act with visible output.
- **Local:** ngrok with a **static domain** (free tier includes one). Without it,
  every tunnel restart is a new URL, meaning a subscriber update and
  re-verification each session.
- **Production:** cloudflared on the self-hosted server. Cutover is one
  subscriber PATCH plus one handshake.
- **Ops surfaces:** Dagster's own UI for fetch failures, push notifications for
  token expiry. No separate status page — it would be redundant.

## Testing

pytest, with priority on the two places where a bug means Google silently
refuses to talk to the service at all:

1. Signature verification (using a locally generated test keyset)
2. The 200/401 verification handshake

Plus replayed notification fixtures and idempotent-upsert tests. These land
**before** a real subscriber is registered — a handshake bug is miserable to
debug live.

## Build order

Progress marker — tick a box only when the step is genuinely complete.
**Each step requires explicit confirmation before implementation.**

- [x] **1. Project skeleton** — monorepo `server/` + `client/`, docker-compose
      Postgres, `.env` scaffold, add `.env` to `.gitignore`
- [x] **2. Google OAuth end to end** — consent flow, encrypted token storage,
      JWT cookie session, one-click re-consent
- [ ] **3. Webhook receiver** — signature verification, 200/401 handshake, 204
      ack, enqueue to pgqueuer, **with pytest coverage**
- [ ] **4. Subscriber CLI + ngrok static domain** — register a real subscriber,
      confirm live notifications land
- [ ] **5. Fetcher worker** — token refresh, `list` on notified interval,
      idempotent upsert, **plus one-off backfill CLI**
- [ ] **6. React dashboard** — steps, sleep, heart rate
- [ ] **7. Dagster** — daily 7-day `:reconcile` job + push alerting on token
      expiry
- [ ] **8. Cutover to cloudflared** — subscriber PATCH to the self-hosted URL

Step 3 precedes step 4 deliberately: verification logic is tested against
fixtures before Google is ever pointed at the endpoint.

The dashboard precedes Dagster by choice; the backfill CLI in step 5 exists so
the dashboard has real data to draw before the recurring job is built.

## Open decisions

Deliberately unresolved — decide these at the step that needs them, with the
user, rather than assuming.

| Decision | Needed by | Notes |
| --- | --- | --- |
| ~~Token encryption library~~ | ~~Step 2~~ | **Settled: not Tink.** `cryptography` AES-256-GCM (`TOKEN_ENCRYPTION_KEY`) and PyJWT HS256 (`SESSION_SECRET`), both plain `openssl rand -hex 32` values. Tink is reserved for verifying Google's published webhook keyset, which needs no secret key material |
| Push alert service | Step 7 | ntfy vs Gotify — likely whichever is already running on the self-hosted box |
| How `client/` is served in production | Step 6 / 8 | Tooling settled at step 1: **Vite + React (JavaScript)**. Still open: static build served from the same host as the API, sharing a registrable domain for cookie auth |
| ~~Role of `google-credentials.json`~~ | ~~Step 2~~ | **Settled: none.** Client ID/secret live in `.env`; the file is kept but unused |

## Deferred

- Chart selection beyond steps / sleep / heart rate
- The ML layer over collected data — `raw_notifications` and the JSONB
  `data_points` already preserve what it will need

## Rejected alternatives

| Rejected | Why |
| --- | --- |
| Apache Kafka, Apache Airflow | Ruled out by the user |
| Temporal | Durable execution, not a DAG engine; heavy self-host footprint |
| RabbitMQ | Second stateful service; loses transactional enqueue |
| TimescaleDB | Earns nothing at single-user volume |
| Fitbit Web API | Superseded by the Google Health API for new projects |
| CASA verification | $500–$4,500 for one user |
| Password auth alongside Google | Doubles auth attack surface, secures nothing extra |
| Opaque session IDs | JWT preferred; revocation is near-worthless at one user |
| 25 typed tables | Premature; display types undecided |
| Notification-level dedupe | Cannot distinguish duplicates from genuine corrections |
| Separate status page | Dagster UI + push alerts already cover it |

## References

- [Google Health API setup](https://developers.google.com/health/setup)
- [Webhook subscriptions](https://developers.google.com/health/webhooks)
- [projects.subscribers](https://developers.google.com/health/reference/rest/v4/projects.subscribers)
- [Data management](https://developers.google.com/health/data-management)
- [OAuth scopes](https://developers.google.com/health/scopes)
- [App verification](https://developers.google.com/health/app-verification)
- [Rate limits](https://developers.google.com/health/rate-limits)
