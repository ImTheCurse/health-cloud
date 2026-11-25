# Operations

Part of the [health-cloud design context](CONTEXT.md). Registering the
subscriber, exposing the endpoint through a tunnel, and where failures surface.

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
- **Ops surfaces:** Prefect's own UI for fetch and backfill failures, push
  notifications for token expiry. No separate status page — it would be
  redundant. The UI is bound to the server's localhost (it has no
  authentication), so it is reached through an SSH tunnel:
  `ssh -L 4200:localhost:4200 ssh-cloud`, then `http://localhost:4200`. The
  hourly `backfill-recent/recent` runs are listed under its deployment; a
  failed one is marked *Failed* and names the types it could not fetch. The
  dashboard's "Backfill today" button starts one on demand and reports
  "Backfill failed" when it fails. See
  [Orchestration](orchestration.md#the-scheduled-backfill).

## Containers

The app runs as three containers beside the infrastructure in
`docker-compose.yml`: `api`, `worker` and `client`. How to run them is in the
[README](../README.md#running-with-docker); why they are shaped this way is
here. Settled 2026-11-24.

- **Two Python images from one Dockerfile.** `api` and `worker` are targets of
  the same multi-stage build, installed with `uv sync --locked`. Only `worker`
  gets the `prefect` group, keeping its ~50 packages out of the web process.
  One-off CLI commands run in the API image with `docker compose run --rm api`.
- **The client is the production build, served by Caddy.** Vite's dev server
  and `vite preview` are not production servers. Caddy needs six lines of
  config, and renders `/config.js` from `API_BASE_URL` with no entrypoint
  script.
- **No hostname is published.** The repository and the images are public, and
  the deployment's hostnames are not. `API_BASE_URL` is read when the client
  container starts rather than compiled into the bundle, so the image names no
  host; docs and `.env.example` use placeholders. The real names live only in
  the server's `.env` and its cloudflared config. A DNS name is still
  resolvable by anyone who already has it; the Cloudflare certificate is a
  wildcard, so certificate transparency logs do not list it.
- **Ports are bound to `127.0.0.1`.** cloudflared runs on the host and reaches
  them there; nothing else needs to.
- **Third-party images are pinned to exact versions**, and upgraded on purpose.
  Only the app's own images follow a moving tag.
- **A hung container restarts itself.** Docker restarts a process that exits
  but only labels a hung one unhealthy. Each app container runs its probe
  through `deploy/healthcheck.sh`, which signals the app after three failures in
  a row — TERM, then KILL — so `restart: unless-stopped` brings it back. It
  needs `init: true`: inside a container, a signal to PID 1 is ignored unless
  the process handles it. The script finds the app as the init process's
  children through `/proc`, because `kill -1` has no spelling that both images'
  shells accept (dash needs `--` before it; BusyBox rejects `--`). An autoheal
  sidecar was turned down because it needs the Docker socket, which is root on
  the host. Verified 2026-11-24 by stopping every process in each container
  with SIGSTOP: all three were restarted within about three minutes.
- **The API's probe is liveness, not readiness.** Restarting the API during a
  Postgres outage fixes nothing and only adds restarts.

### Images and updates

- **Published to GHCR by CI** once the test jobs pass, `linux/amd64` only. A
  push to `main` publishes `sha-<short>`; a hand-cut `vX.Y.Z` tag publishes
  `X.Y.Z`, `X.Y` and `latest`.
- **The server follows `latest`** with a timer that runs
  `docker compose pull && docker compose up -d`, which recreates only the
  services whose image changed. Each update costs a few seconds of downtime;
  nothing is lost in it, since Google redelivers webhooks for 7 days and an
  unacknowledged message stays queued. Zero-downtime rollouts (a proxy plus
  `docker rollout`, or Swarm's start-first updates) were considered and judged
  not worth their setup at one user.
- **The server holds no checkout.** It needs `docker-compose.yml`, `.env` and
  `service-account.json`, nothing else; a release that changes the compose file
  is copied over by hand. The timer and the boot unit belong to the repository
  that manages the server's other services. See
  [Decisions](decisions.md#deferred).
