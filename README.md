# health-cloud

A self-hosted pipeline for personal Google Health data. It receives change
notifications from Google, fetches the measurements from the Google Health API,
stores them encrypted in Postgres, and presents them in a React dashboard.

It supports any device that syncs to Google Health: Fitbit trackers, Pixel
Watch, and other Google Health app devices. It is built for a single user, runs
locally during development, and is designed for deployment on a self-hosted
server.

## Screenshots

The home page shows the day's key figures against the 7-day average and the
usual range:

![Home page of daily figures](docs/images/home.png)

A single day of heart rate at five-minute resolution, over the heart-rate zones:

![Heart rate over one day](docs/images/heart-rate-day.png)

Resting heart rate over a month, against the personal range:

![Resting heart rate over a month](docs/images/resting-heart-rate-month.png)

## Features

- **Push-based ingestion.** Google's webhook notifications are verified,
  recorded and queued durably before they are acknowledged, so a crash never
  loses an update.
- **Idempotent fetching.** A Prefect flow pulls the notified intervals from the
  Health API and upserts them, so replays and retries never duplicate data.
- **Backfill CLI.** Fills history or gaps directly from the API, a day at a
  time.
- **Encryption at rest.** Every stored health value, and the OAuth tokens, are
  encrypted with AES-256-GCM in the application. The database never holds
  plaintext measurements.
- **Read-only access.** The app requests read-only Health API scopes and never
  writes back to Google.
- **Dashboard.** Heart rate, HRV, sleep, breathing and blood oxygen, activity,
  exercise, running, nutrition and body measurements, over a single day, a week,
  a month, three months or a custom range.

## Architecture

```mermaid
flowchart TD
    G["Google Health"]
    R["Webhook receiver<br/>verify signature, audit row,<br/>publish, 204"]
    N["NATS JetStream<br/>file-backed work queue"]
    F["Prefect fetcher flow<br/>refresh token, list dataPoints,<br/>upsert, then ack"]
    DB[("Postgres<br/>encrypted values")]
    API["FastAPI read API"]
    UI["React dashboard"]

    G -- "webhook: change pointers" --> R
    R -- "one message per pointer" --> N
    R -. "trigger a run, after the 204" .-> F
    N -- "durable pull consumer" --> F
    F -- "list dataPoints" --> G
    F --> DB
    DB --> API
    API --> UI
```

Google's webhook delivers **change pointers, not health data**: it says that a
data type changed for a user over an interval, and the values must then be
fetched from the Health API. The design follows from that:

1. **The receiver** verifies the request signature, writes an audit row,
   publishes one message per change pointer to NATS JetStream, and only then
   answers `204`. Any failure answers `503`, so Google redelivers. It does
   nothing slow or fragile.
2. **The fetcher**, a Prefect flow, drains the queue. It refreshes the OAuth
   token, lists the notified interval from the Health API, handles pagination
   and rate limits, upserts the rows, and acknowledges each message only after
   its rows are committed.
3. **Storage** is organised by the shape of the data in time (instantaneous
   samples, intervals, sessions with segments, and daily values) rather than by
   data type. Types the schema does not model yet land intact in a catch-all
   table.
4. **The read API** decrypts and aggregates in Python, since encrypted values
   cannot be summed in SQL, and serves only the columns each chart needs.
5. **The dashboard** fetches through a small in-memory cache that refreshes in
   the background. It never writes health data to browser storage.

## Tech stack

| Area | Choice |
| --- | --- |
| Backend | Python 3.13, FastAPI, SQLModel, `psycopg` (synchronous) |
| Database | Postgres 17 |
| Queue | NATS JetStream, file storage |
| Orchestration | Prefect 3, self-hosted |
| Auth | Google OAuth (`google-auth-oauthlib`), HS256 JWT session cookie |
| Cryptography | `cryptography` AES-256-GCM; Tink for Google's webhook signatures |
| Frontend | React 19, Vite, MUI, nivo charts, plain JavaScript |
| Tooling | uv, pytest, mypy, oxlint, Docker Compose |

## Repository layout

```
server/              FastAPI backend, imported as server.<module>
  api/               HTTP routes: auth, webhooks, health checks, /data reads
  auth/              OAuth flow, sessions, users
  crypto/            token, session and health-value encryption
  db/                engine, sessions, upserts, read repository
  models/            SQLModel tables
  webhooks/          signature verification and payload parsing
  queue/             NATS JetStream publishing and consuming
  health/            Google Health API client
  flows/             Prefect fetcher and heart-rate rollup flows
  rollup/            hourly heart-rate summaries: rebuilding and reading
  aggregation/       bucketing and summaries for the read API
  cli.py             subscriber, database, backfill and rollup commands
client/              React dashboard (Vite)
tests/               pytest suite, mirroring server/
docs/                design documents
docker-compose.yml   Postgres, NATS, Prefect and Prefect's database
```

## Getting started

### Prerequisites

- [uv](https://docs.astral.sh/uv/)
- Docker with Docker Compose
- Node.js and npm
- A Google Cloud project with the Google Health API enabled, an OAuth client
  for a web application, and a service account for managing the webhook
  subscriber. See [Google Health API setup](https://developers.google.com/health/setup).
- For live notifications during development, a public HTTPS URL that forwards
  to the local server, such as an [ngrok](https://ngrok.com/) static domain.

### 1. Configure

```bash
cp .env.example .env
```

Fill in `.env`. Every setting is required, and each one is described in
`.env.example`. Generate the three secrets with:

```bash
openssl rand -hex 32   # once each for TOKEN_ENCRYPTION_KEY, SESSION_SECRET, DATA_ENCRYPTION_KEY
```

Keep `DATA_ENCRYPTION_KEY` safe: without it the stored measurements cannot be
read.

### 2. Start the services

```bash
docker compose up -d     # Postgres :5432, NATS :4222, Prefect :4200
uv sync                  # backend dependencies
uv run uvicorn server.main:app --workers 3
```

Run the API with several workers. Reads decrypt in Python on one core per
worker, so a single worker busy with a long heart-rate read would hold up every
other request.

Health checks:

- `GET /healthz`: liveness
- `GET /readyz`: readiness, which checks both Postgres and NATS

### 3. Start the fetcher

`prefect` is in its own dependency group, so the web process never installs it.
In a separate terminal, run and leave running:

```bash
uv run --group prefect python -m server.flows.fetch deploy
```

This registers the `fetcher` and `rollup-heart-rate/rollup` deployments and
serves their runs. Put the fetcher's deployment ID it prints into
`PREFECT_DEPLOYMENT_ID` in `.env`, then restart the API. The rollup deployment
is found by name and needs no setting.

To drain the queue once without serving a deployment:

```bash
uv run --group prefect python -m server.flows.fetch
```

### 4. Start the dashboard

```bash
cd client
npm install
npm run dev
```

Open <http://localhost:5173> and choose **Connect Google Health**. Google shows
an "unverified app" warning, since the OAuth client is private and has not been
through Google's app verification.

### 5. Register the webhook subscriber

With the API reachable at `WEBHOOK_PUBLIC_URL`:

```bash
uv run python -m server.cli subscriber create
uv run python -m server.cli subscriber sync-types   # subscribe to every data type
uv run python -m server.cli subscriber list
```

`subscriber patch` repoints the registration at a new URL, for example when
moving from a development tunnel to production.

### 6. Backfill history

Google only notifies about new changes, so fill past data directly:

```bash
uv run python -m server.cli backfill run --types steps sleep heart-rate --days 7
```

Data type ids are kebab-case (`heart-rate`, not `heart_rate`). Heart rate is
about 34,000 points a day, and the Health API keeps only about a week of it.
A backfill that includes heart rate ends by starting a rollup run, which
rebuilds the hourly summaries the long heart-rate charts read; it needs the
Prefect deployments served.

## Development

```bash
uv run mypy          # type check, run first in CI
uv run pytest        # test suite
cd client && npm run lint && npm run build
```

Tests under `tests/integration/` use real Postgres and NATS, with a throwaway
database and their own stream. They are skipped when the services are not
running, and always run in CI.

Other commands:

```bash
uv run python -m server.cli db reset-measurements   # drop and recreate the measurement tables; users are kept
uv run python -m server.cli rollup rebuild --days 120   # rebuild the hourly heart-rate summaries from stored samples
```

## Security

- Health values, OAuth tokens and the raw notification log are encrypted at
  rest with AES-256-GCM, using separate keys for tokens and health data.
- Webhook requests are authenticated with a shared secret and verified against
  Google's published signing keys.
- Sessions are HS256-signed, HTTP-only cookies. Credentialed requests are
  accepted only from the origins in `CORS_ORIGINS`.
- NATS and Prefect have no authentication of their own and are bound to
  localhost.
- Logs never contain health values or personal details.

## Documentation

The design is documented in [`docs/`](docs/). Start with
[`docs/CONTEXT.md`](docs/CONTEXT.md), which covers the architecture and the build
order, and links to a document for each area:

| Document | Covers |
| --- | --- |
| [Stack](docs/stack.md) | Library choices and code conventions |
| [Ingestion](docs/ingestion.md) | Webhook payloads and signature verification |
| [Orchestration](docs/orchestration.md) | NATS, Prefect and delivery guarantees |
| [Data model](docs/data-model.md) | Tables and upserts |
| [Authentication](docs/auth.md) | OAuth, sessions and token storage |
| [Encryption](docs/encryption.md) | Encryption at rest |
| [Observability](docs/observability.md) | Logging and error handling |
| [Testing](docs/testing.md) | Test strategy and fixtures |
| [Operations](docs/operations.md) | Subscriber management and deployment |
| [Charting](docs/charting.md) | The dashboard |
| [Decisions](docs/decisions.md) | Open, deferred and rejected decisions |

## Status

The ingestion pipeline, encryption and read API are complete. The dashboard is
being reworked around a home page of daily figures. Still to come: stored hourly
heart-rate summaries for long ranges, a scheduled daily reconciliation with
alerts on token expiry, and production deployment behind Cloudflare Tunnel.
