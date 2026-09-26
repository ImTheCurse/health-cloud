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
- **Ops surfaces:** Prefect's own UI for fetch failures, push notifications for
  token expiry. No separate status page — it would be redundant.
