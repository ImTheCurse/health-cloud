# The API and the Prefect worker: `--target api` or `--target worker`.
# Only the worker installs the prefect group.

FROM python:3.13-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.7.2 /uv /usr/local/bin/uv
RUN useradd --system --create-home app
WORKDIR /app
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1
COPY deploy/healthcheck.sh /usr/local/bin/healthcheck
COPY deploy/probe.py /usr/local/bin/probe.py
COPY pyproject.toml uv.lock ./

FROM base AS api
RUN uv sync --locked --no-dev --no-install-project
COPY server ./server
USER app
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "3"]

FROM base AS worker
RUN uv sync --locked --no-dev --no-install-project --group prefect
COPY server ./server
USER app
CMD ["python", "-m", "server.flows.fetch", "deploy"]
