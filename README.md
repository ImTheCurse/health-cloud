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
docker compose up -d     # Postgres :5432, NATS :4222, Prefect :4200 (+ its own db)
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

### Fetching the data

The receiver only queues change pointers; a Prefect flow turns them into rows.
`prefect` is in its own dependency group, so the flow needs `--group prefect` and
the web process never installs it. `docker compose up -d` starts Prefect's server
and services, **not** the fetcher. In a separate terminal, run and leave running:

```bash
uv run --group prefect python -m server.flows.fetch deploy
```

This registers the `fetcher` deployment and serves its runs. Copy the deployment
ID it prints into `PREFECT_DEPLOYMENT_ID` in `.env` (replace `pending`), then
restart the FastAPI process so it picks up the new value. If webhook requests
return 204 but log `could not start a fetcher run: Prefect answered 404`, check
that the ID matches the deployment registered on the Prefect server at
`PREFECT_API_URL`. A 204 means the notifications are already persisted in NATS;
the failed trigger has not discarded them, and a later fetcher run can drain the
queue.

To drain the queue once without registering or serving a deployment:

```bash
uv run --group prefect python -m server.flows.fetch
```

Nothing notified us about the past, so a first fill or a gap is a direct fetch that
bypasses the queue entirely — a day at a time, committing as it goes:

```bash
uv run python -m server.cli backfill run --types steps sleep heart-rate --days 7
# Floors has no list endpoint; its daily civil-date totals use dailyRollUp.
uv run python -m server.cli backfill run --types floors --days 7
```

Data type ids are **kebab-case** (`heart-rate`, not `heart_rate`). Expect volume:
heart rate is roughly 34,000 points a day.

## A note on the data flow

Google's webhook delivers **change pointers, not health data** — it reports
that a data type changed for a user over an interval, and the server then
queries the Health API for the values. The receiver's only job is to verify the
signature, record the delivery, publish the pointers, and only then return
`204`. That order is the durability guarantee: nothing is acknowledged to Google
until it has been written down and confirmed persisted by the broker, and any
failure answers `503` so Google redelivers. See
[`docs/orchestration.md`](docs/orchestration.md).
