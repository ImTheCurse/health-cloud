# Authentication and token lifetime

Part of the [health-cloud design context](CONTEXT.md). One Google flow covers
both sign-in and Health consent, and the 7-day refresh-token expiry that follows
from it is the constraint the rest of the design is shaped around.

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

So a single recurring Prefect flow — *"reconcile the last 7 days for every data
type"* — covers first-connect backfill, post-re-consent gap recovery, and
anything the webhook dropped. See [Orchestration](orchestration.md) for what
runs it.
