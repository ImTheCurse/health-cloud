# Observability

Part of the [health-cloud design context](CONTEXT.md). One structured record
per request, what it carries, and the things that must never appear in it.

**loguru**, configured once in `server/config/logging.py`. Human-readable and
colourised when `ENVIRONMENT=local`, structured JSON everywhere else — the same
fields either way, so a line read in a terminal is the line an aggregator would
parse. `diagnose=False` on the JSON sink is deliberate: loguru's diagnostic
tracebacks inline local variable values, which on these paths would put
notification bodies and decrypted tokens in the log.

**One aggregated record per request**, not a line per thing that happened. The
middleware (`@app.middleware("http")`, per FastAPI's documented form) builds a
`RequestLog` and emits it once in a `finally`, so a request that raised still
produces a line carrying `message` and `cause`:

```
request_id, method, path, status, duration_ms, is_secure,
x_forwarded_for, user, events[], error{message, cause}
```

`RequestLog` is a class holding both the fields and the ways of adding to them,
so a route writes `log.add_event(name, **fields)` and `log.set_user(id)`. It
lives on **`request.state`** for the life of the request, and a route receives
it as a declared dependency (`RequestLogDep`) rather than by being handed a
`Request` it has no other use for — the webhook receiver took `request` solely
to log, and no longer takes it at all.

Nothing is ambient: two requests in flight hold unrelated records, because each
wraps its own ASGI scope. A concurrency test asserts that directly, and was
confirmed to fail when the dependency is made to return one shared record.

A route reached **without the middleware mounted** — the normal case in a test
exercising a route directly — gets a *detached* record from
`RequestLog.unlogged()`. Adding to it is harmless rather than special-cased:
nothing emits it, so it is discarded with the request. That is why no method has
to ask whether it is real, and why no call site needs a None check.

`request_id` is generated per request and echoed as `X-Request-ID`. An inbound
one is **ignored**: this endpoint is internet-facing, and trusting a caller's
id would let them forge or collide correlation.

`user` is a six-hex-character SHA-256 truncation of `healthUserId`, computed on
demand and **not stored** — it is a pure function, so it can always be
recomputed to identify which user a line refers to. A raw health user id,
combined with a data type and a timestamp, *is* a health record.

**Never logged, unconditionally:** request and response bodies, `Authorization`,
cookies, and the signature header. Prefect task progress follows the same
principle: log only data types, counts, hashed user handles and error classes,
not notification bodies, measurements, credentials, or raw user ids.

**Log level is a per-route policy, not sampling.** Nothing is discarded and
nothing is decided by chance; the policy only chooses a level, and a `DEBUG`
record is still there for anyone who lowers the threshold. The default is
`ALWAYS`, so a new route is logged in full from the day it is written and going
quiet is a visible decision in the source:

```python
@router.get("/healthz")
@log_policy(QUIET)
def healthz() -> dict[str, str]: ...
```

A `QUIET` route drops routine successes to `DEBUG` but still speaks up on
`status >= 400`, an exception, or any domain event. Only `/healthz` and
`/readyz` are quiet today. Locally everything is `INFO` regardless.

uvicorn's own loggers are left alone, so each request currently produces **two**
lines — uvicorn's access line and ours. Collapsing them is a small
`InterceptHandler` change if the duplication becomes annoying.
