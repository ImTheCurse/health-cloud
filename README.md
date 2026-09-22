# health-cloud

Self-hosted pipeline that ingests Google Health data (Fitbit trackers, Pixel
Watch, and other Google Health app devices), stores it in Postgres, and
displays it in a React dashboard. Single user.

**Read [`docs/CONTEXT.md`](docs/CONTEXT.md) first** — it holds the agreed
architecture, why each decision was made, what was rejected, and the build
order with progress checkboxes.

## Layout

```
server/          FastAPI backend - import root, addressed as server.module.submodule
  config/        settings (all env vars required, no defaults)
  db/            engine and sessions
  models/        SQLModel tables
  api/           routers
client/          React dashboard (JavaScript, Vite)
tests/           pytest
docs/            design context
```

The backend is **synchronous and SQLModel-only**: SQLModel ships no async
engine, so async would mean importing SQLAlchemy directly. Driver is `psycopg`.
Outbound HTTP uses `requests`.

## Local development

Requires [uv](https://docs.astral.sh/uv/), Docker, and Node.

```bash
cp .env.example .env     # then fill in as later steps need values
docker compose up -d     # Postgres on :5432
uv sync                  # backend dependencies
uv run uvicorn server.main:app --reload
```

- `GET /healthz` — liveness, touches nothing
- `GET /readyz` — readiness, checks the database

Tests:

```bash
uv run pytest
```

Frontend:

```bash
cd client && npm install && npm run dev
```

## A note on the data flow

Google's webhook delivers **change pointers, not health data** — it reports
that a data type changed for a user over an interval, and the server then
queries the Health API for the values. The receiver's only job is to verify the
signature, return `204`, and enqueue. See `docs/CONTEXT.md`.
