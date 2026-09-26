# Testing

Part of the [health-cloud design context](CONTEXT.md). Where the coverage is
deliberately concentrated, and the three rules learned from tests that passed
while protecting nothing.

pytest, with priority on the two places where a bug means Google silently
refuses to talk to the service at all:

1. Signature verification (using a locally generated test keyset)
2. The 200/401 verification handshake

Plus replayed notification fixtures and idempotent-upsert tests. These land
**before** a real subscriber is registered — a handshake bug is miserable to
debug live.

**Test behaviour, not logging.** Assert the exception a function raises and the
status a route returns; do not assert that a function logged. The exception is
what the rest of the system reacts to, and a test that pins log wording breaks
on every rewording while protecting nothing. The deliberate exception is a
small set asserting that sensitive values — notification bodies, the shared
secret, the signature, the raw health user id — **never reach a log**, which is
a security property rather than a message format.

**Fixtures must match what Google really sends.** The payload-shape bug above
survived a green suite because the fixture was the shape we imagined. Test
doubles are built from captured live traffic, with every real identifier
replaced by an invented one of the same form (`FAKE_HEALTH_USER_ID`,
`FAKE_PROJECT_NUMBER`, `FAKE_RECORD_ID` in `tests/google_webhook.py`) so no
account, record or sleep time reaches the repository.

**A test that cannot fail is not a test.** Leakage assertions first check that
something *was* logged, or they pass vacuously; a tamper-detection test checks
that the body it altered actually differs. Both guards were added after the
real versions silently stopped testing anything.
