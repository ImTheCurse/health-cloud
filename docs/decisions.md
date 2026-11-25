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
| Push alert service | Step 11 | ntfy vs Gotify — likely whichever is already running on the self-hosted box |
| ~~How `client/` is served in production~~ | ~~Step 9~~ | **Settled 2026-11-24.** The `vite build` output, served by Caddy from its own image on its own hostname, sharing a registrable domain with the API for cookie auth. The API address is not built in: Caddy serves it as `/config.js` from `API_BASE_URL`, so the public image names no hostname. See [Operations](operations.md#containers) |
| ~~Role of `google-credentials.json`~~ | ~~Step 2~~ | **Settled: none.** Client ID/secret live in `.env`; the file is kept but unused |
| ~~Logging~~ | ~~Step 3~~ | **Settled: loguru**, one aggregated record per request on `request.state`, per-route level policy defaulting to full. See [Observability](observability.md) |
| ~~Storing a log-safe user handle~~ | ~~Step 3~~ | **Settled: not stored.** A truncated SHA-256 of `healthUserId` is a pure function, so it is recomputed on demand — no column, no migration |
| ~~Orchestrator~~ | ~~Step 9~~ | **Settled 2026-09-25: Prefect**, self-hosted. See [Orchestration](orchestration.md) |
| ~~Stream configuration~~ | ~~Step 3~~ | **Settled 2026-09-25.** Stream `health`; subjects `health.notifications.<dataType>`, with an unrecognised type going to `…unknown`; file storage; `WORK_QUEUE` retention; `allow_direct` only when `ENVIRONMENT` is `local`. No `max_age` — nothing ages out, a message leaves when a consumer acks it. Revisit once real volume is visible |
| ~~Consumer configuration~~ | ~~Step 5~~ | **Settled 2026-09-28.** Durable pull consumer `fetcher`, batches of 50 drained until empty, `ack_wait` 60s, `max_deliver` 5, explicit per-message acks. Retries live here rather than in Prefect: JetStream's redelivery survives the process dying |
| NATS authentication | Step 10 | **None deliberately, for now.** The port is published as `127.0.0.1:${NATS_PORT}` in `docker-compose.yml`, so the broker is not reachable off the box and credentials buy nothing yet. They become necessary at cutover, when the host is exposed |
| ~~Queue technology~~ | ~~Step 3~~ | **Settled 2026-09-25: NATS JetStream**, file storage. See [Orchestration](orchestration.md) and [the stack rationale](stack.md) |
| ~~How durability is guaranteed~~ | ~~Step 3~~ | **Settled: ordering, not atomicity.** No broker can join our transaction; commit → publish → `PubAck` → 204, and 503 otherwise, loses nothing given Google's 7-day retry |
| ~~What a failed flow trigger means~~ | ~~Step 5~~ | **Settled 2026-09-28: swallowed.** The trigger is a payload-free doorbell fired from a `BackgroundTask` after the 204, so it cannot delay the acknowledgement and its failure costs latency rather than data. The interval sweep that makes that honest belongs to step 11 |
| A table for daily summaries | When a chart needs one | `daily-*` types carry a bare `date` -- a fourth time shape. They land in `unknown_data_points` with their date read into `civil_date`, so they are queryable, and every dashboard chart reads them fine from there. Promote to their own table if a chart needs one |
| Rollup-only data types | Step 8 or 9 | `floors`, `total-calories` and `calories-in-heart-rate-zone` support no `list`, only `rollUp`/`dailyRollUp`. `floors` now uses `dailyRollUp` and lands in `unknown_data_points`; **total-calories and calories-in-heart-rate-zone remain uncollected**. Google serves only a few months of history, so the gap is recoverable only for a while; they still need a second read path |
| Unfiltered high-frequency fetches | Step 11 | `heart-rate` and most other types accept no time filter, so a small interval is served by paging from now backwards until past the window. Correct, and wasteful: one hour of heart-rate scanned ~70,000 points to keep 52. Revisit if `reconcile` or `rollup` can narrow it |
| Whether `recordId` is stable | Step 8 | Moot for fetched points -- Google sends no id, so ours is derived from the window and source. Still open for the webhook's `recordId`, which nothing reads yet |
| ~~Encryption at rest~~ | ~~Step 6~~ | **Settled 2026-11-01.** Against someone who obtains the app database (SQL injection, leaked credentials, a dump) — disk theft and host root out of scope, since the key sits in `.env`. Application-level AES-256-GCM with `DATA_ENCRYPTION_KEY`, via a lazily-resolved `TypeDecorator`; every value encrypted, structure plaintext; version byte, zlib on JSON columns, no associated data; app database only. See [Encryption at rest](encryption.md) |
| Combining sources | Before a chart needs a non-Fitbit source | Steps, distance and exercise arrive from Fitbit and from Apple HealthKit (including Nike Run Club), overlapping in time, so summing every source double-counts. Reads use `FITBIT` and `GOOGLE_HEALTH` only for now. Merging, averaging, or using Google's own deduplicated `dailyRollUp` totals is undecided. See [Data model](data-model.md) |
| Sampling the request log | When log volume is visible | Every route logs at `ALWAYS` today. Which routes, if any, should move to sampling — the read API is the likely candidate — is undecided. See [Observability](observability.md) |
| Short awakenings stored as sleep stages | When `session_segments` is read for sleep | `shortAwakenings` map to `SegmentType.SLEEP_STAGE`, and Google labels them `LIGHT`, so they overlap the real stages in `session_segments`. The sleep read builds stages from the session's `value` and takes minutes per stage from Google's `stagesSummary`, so nothing reads them yet. The fix is a segment type of their own, re-derived from `raw` |
| ~~Deep historical backfill~~ | ~~Before Google stops serving the oldest days~~ | **Settled 2026-11-16.** Types Google cannot filter by time are backfilled in **one backward pass** from now to the start of the window, committing each day as the pass leaves it, with the token re-checked before every page and the page limit scaled to the window (50 per day). The five filterable types still go a day at a time. Heart-rate is kept at full resolution for the whole window. `list` serves roughly 4 months back (steps from 120 days, none from 365, probed 2026-11-01) |
| Alembic | Before step 10, or before stored history outgrows what Google serves — whichever comes first | Not yet. Until then a schema change drops the affected tables (`db reset-measurements`) and re-backfills, which is cheap while Google can serve everything stored. It stops being cheap at production cutover, and once the oldest stored data is older than Google's ~4 months of history. Adopting later costs a baseline autogenerated from the models plus `alembic stamp head` |
| ~~Postgres in CI~~ | ~~Step 3~~ | **Settled 2026-09-25: yes.** A `postgres:17-alpine` service plus `pgq install` on the `backend-api` job. Declined earlier only while nothing touched a database |

## Deferred

- **Expected values from an ML model** drawn on the charts, and a **recovery
  check** of training load against next-morning HRV. See
  [Charting](charting.md#deferred)
- **A secret manager** for `DATA_ENCRYPTION_KEY`, `TOKEN_ENCRYPTION_KEY` and
  `SESSION_SECRET`, so a stolen disk or a compromised host no longer yields the
  keys — the threats [encryption at rest](encryption.md) leaves out of scope.
  Revisit NATS and the Prefect database with it
- **Binding ciphertexts to their rows** (AES-GCM associated data), so a SQL
  *write* cannot swap encrypted values between rows undetected
- **Backfill as a durable workflow.** `backfill run` is a CLI that runs in the
  foreground: an interrupted run keeps every committed day but restarts from
  "now", and nothing retries it or records how far it got. The hourly
  `backfill-recent` flow covers the last day on a schedule; a long backfill
  still runs from the CLI. Making that one durable means per-type progress,
  retries and a resumable cursor
- **Filter fields for more types.** Only five types have a verified filter
  field. Probing the others would let them be fetched a day at a time, which is
  cheaper still than one backward pass
- **Alerting on a crashed rollup run.** A `rollup-heart-rate` run that
  Prefect marks *Crashed* (its worker died) is not retried, so its hours stay
  stale until the step 11 rebuild or a manual `rollup rebuild`. A notification
  on crashed and failed runs belongs with step 11's push alerting; a Prefect
  automation that reruns them is the other option, and adds setup outside the
  repo
- **Binding Postgres to `127.0.0.1`** and replacing the default password — it
  is published on every interface today. The user's own task
- **Automatic rollback of a failed update.** The server pulls `latest` and
  recreates whatever changed; a release whose containers never become healthy
  stays broken until the previous version is pinned with `APP_VERSION`.
  Releases are tagged by hand, so someone is around when one goes out
- **The server's updater and boot unit** live in the separate repository that
  holds the server's other services, not here: a systemd timer running
  `docker compose pull && docker compose up -d`, and a oneshot unit running
  `docker compose up -d` at boot. Written at the step 10 cutover
- The ML layer over collected data — `raw_notifications` and the `raw` column
  of every [measurement table](data-model.md) already preserve what it will need

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
| Full-disk / volume encryption (LUKS) for health data | Postgres decrypts for any querying client, so it does not stop SQL injection or leaked credentials |
| `pgcrypto` | The key travels inside SQL, reachable through `pg_stat_statements`, logs and injection |
| TDE (`pg_tde`, EDB) | Not in vanilla Postgres 17; and, like LUKS, decrypts for any querying client |
| An explicit cipher collaborator at each read and write site | Turns model fields into `bytes` and every read site into a place to forget a decrypt; a `TypeDecorator` keeps types and is resolved lazily |
| Separate status page | Prefect UI + push alerts already cover it |
