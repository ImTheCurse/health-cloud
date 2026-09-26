# health-cloud

Self-hosted pipeline that ingests Google Health data (Fitbit trackers, Pixel
Watch, and other Google Health app devices), stores it in Postgres, and
displays it in a React dashboard. Single user.

**Read [`docs/CONTEXT.md`](docs/CONTEXT.md) first** — it holds the agreed
architecture, the stack, and the build order with progress checkboxes, and it
indexes a design doc per area (ingestion, orchestration, data model, auth,
observability, testing, operations, and the open/rejected decisions).

## Layout

```
server/          FastAPI backend - import root, addressed as server.module.submodule
  config/        settings (all env vars required, no defaults)
  db/            engine and sessions
  models/        SQLModel tables
  api/           routers
client/          React dashboard (JavaScript, Vite)
tests/           pytest, mirroring server/ one package per module
docs/            design context
```

Tests live in the package matching the code they cover (`tests/crypto/`,
`tests/webhooks/`), split into files by what they exercise rather than one file
per module. Shared test doubles are plain modules, not conftests:
`tests/google_webhook.py` (throwaway signing keys and sample bodies) and
`tests/webhooks/fakes.py` (a fake transport for the subscriber API).

The backend is **synchronous and SQLModel-only**: SQLModel ships no async
engine, so async would mean importing SQLAlchemy directly. Driver is `psycopg`.
Outbound HTTP uses `requests`.

## Local development

Requires [uv](https://docs.astral.sh/uv/), Docker, and Node.

```bash
cp .env.example .env     # then fill in as later steps need values
docker compose up -d     # Postgres on :5432, NATS (JetStream) on :4222
uv sync                  # backend dependencies
uv run uvicorn server.main:app --reload
```

- `GET /healthz` — liveness, touches nothing
- `GET /readyz` — readiness, checks Postgres **and** the broker, because the
  receiver refuses to acknowledge a notification unless both are working

Types and tests:

```bash
uv run mypy      # what CI runs first
uv run pytest
```

Tests under `tests/integration/` need Postgres and NATS running; they skip when
neither is reachable, and CI always runs them. They use a throwaway database and
their own stream.

Frontend:

```bash
cd client && npm install && npm run dev
```

## A note on the data flow

Google's webhook delivers **change pointers, not health data** — it reports
that a data type changed for a user over an interval, and the server then
queries the Health API for the values. The receiver's only job is to verify the
signature, record the delivery, publish the pointers, and only then return
`204`. That order is the durability guarantee: nothing is acknowledged to Google
until it has been written down and confirmed persisted by the broker, and any
failure answers `503` so Google redelivers. See
[`docs/orchestration.md`](docs/orchestration.md).
