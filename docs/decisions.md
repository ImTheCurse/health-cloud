# Decisions: open, deferred, rejected

Part of the [health-cloud design context](CONTEXT.md). Three indexes over the
whole design, kept together on purpose: what is still undecided, what is
postponed, and what was considered and turned down. Struck-through rows are
settled — they stay so a decision is not relitigated, and so the reason survives.

## Open decisions

Deliberately unresolved — decide these at the step that needs them, with the
user, rather than assuming.

| Decision | Needed by | Notes |
| --- | --- | --- |
| ~~Token encryption library~~ | ~~Step 2~~ | **Settled: not Tink.** `cryptography` AES-256-GCM (`TOKEN_ENCRYPTION_KEY`) and PyJWT HS256 (`SESSION_SECRET`), both plain `openssl rand -hex 32` values. Tink is reserved for verifying Google's published webhook keyset, which needs no secret key material |
| Push alert service | Step 7 | ntfy vs Gotify — likely whichever is already running on the self-hosted box |
| How `client/` is served in production | Step 6 / 8 | Tooling settled at step 1: **Vite + React (JavaScript)**. Still open: static build served from the same host as the API, sharing a registrable domain for cookie auth |
| ~~Role of `google-credentials.json`~~ | ~~Step 2~~ | **Settled: none.** Client ID/secret live in `.env`; the file is kept but unused |
| ~~Logging~~ | ~~Step 3~~ | **Settled: loguru**, one aggregated record per request on `request.state`, per-route level policy defaulting to full. See [Observability](observability.md) |
| ~~Storing a log-safe user handle~~ | ~~Step 3~~ | **Settled: not stored.** A truncated SHA-256 of `healthUserId` is a pure function, so it is recomputed on demand — no column, no migration |
| ~~Orchestrator~~ | ~~Step 7~~ | **Settled 2026-09-25: Prefect**, self-hosted. See [Orchestration](orchestration.md) |
| ~~Stream configuration~~ | ~~Step 3~~ | **Settled 2026-09-25.** Stream `health`; subjects `health.notifications.<dataType>`, with an unrecognised type going to `…unknown`; file storage; `WORK_QUEUE` retention; `allow_direct` only when `ENVIRONMENT` is `local`. No `max_age` — nothing ages out, a message leaves when a consumer acks it. Revisit once real volume is visible |
| Consumer configuration | Step 5 | `ack_wait`, `max_deliver` and the batch size the flow pulls. Deliberately not chosen at step 3: no consumer exists yet, and these only mean something against a flow whose runtime is known |
| NATS authentication | Step 8 | **None deliberately, for now.** The port is published as `127.0.0.1:${NATS_PORT}` in `docker-compose.yml`, so the broker is not reachable off the box and credentials buy nothing yet. They become necessary at cutover, when the host is exposed |
| ~~Queue technology~~ | ~~Step 3~~ | **Settled 2026-09-25: NATS JetStream**, file storage. See [Orchestration](orchestration.md) and [the stack rationale](stack.md) |
| ~~How durability is guaranteed~~ | ~~Step 3~~ | **Settled: ordering, not atomicity.** No broker can join our transaction; commit → publish → `PubAck` → 204, and 503 otherwise, loses nothing given Google's 7-day retry |
| What a failed flow trigger means | Step 5 | Whether a failed `run_deployment` is swallowed because the queue is the source of truth, and whether the deployment also carries an interval schedule as a sweep |
| ~~Postgres in CI~~ | ~~Step 3~~ | **Settled 2026-09-25: yes.** A `postgres:17-alpine` service plus `pgq install` on the `backend-api` job. Declined earlier only while nothing touched a database |

## Deferred

- Chart selection beyond steps / sleep / heart rate
- The ML layer over collected data — `raw_notifications` and the JSONB
  [`data_points`](data-model.md) already preserve what it will need

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
