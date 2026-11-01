# Encryption at rest

Part of the [health-cloud design context](CONTEXT.md). Agreed 2026-11-01. What is
encrypted in the app database, against whom, and how — and what is deliberately
left in plaintext.

## Threat model

**Defended:** someone who obtains the app database without the application — a
SQL injection that reads rows, leaked database credentials, a `pg_dump` that ends
up somewhere it should not.

**Out of scope, deliberately:**

- **Disk or backup theft, and root on the host.** The key lives in `.env` on the
  same machine, so anyone holding the disk or the host holds the key too.
  Keeping the key off the box is the [secret manager](decisions.md#deferred)
  item, not this design.
- **NATS and the Prefect database.** Neither is reachable through the app
  database. NATS holds change pointers — type, interval, user — and no values,
  and only until they are acked; Prefect's database holds flow runs whose logs
  already exclude health data (see [Observability](observability.md)). The data
  is valuable as a whole; these fragments are not worth the complexity yet.
- **Activity patterns in plaintext structure.** Timestamps and data types stay
  readable, so an attacker learns *that* a sleep session ran 23:40–07:10, not
  what it contained. Accepted: it is what keeps indexes and window queries
  working.

## Where it happens

**In the application**, with `cryptography` AES-256-GCM, before the write and
after the read. The key never enters Postgres. The alternatives fail this threat
model:

| Rejected | Why |
| --- | --- |
| Full-disk / volume encryption (LUKS) | Postgres hands decrypted rows to anyone who can query it — no defence against SQL injection or leaked credentials |
| `pgcrypto` | The key travels inside SQL, where `pg_stat_statements`, server logs and an injection can reach it |
| TDE (`pg_tde`, EDB) | Not in vanilla Postgres 17, so it breaks *plain Postgres*; and like LUKS, it decrypts for any querying client |

The key is **`DATA_ENCRYPTION_KEY`**, a plain `openssl rand -hex 32` value,
separate from `TOKEN_ENCRYPTION_KEY`. The token cipher, its format and its
callers are untouched.

## What is encrypted

Every **value**; none of the **structure**.

| Encrypted | Plaintext |
| --- | --- |
| `value_numeric`, `value_unit` — uncompressed | `health_user_id`, `data_type`, `record_id` — the natural key and `ON CONFLICT` target |
| `value`, `raw` — zlib, then encrypted | `start_ts`/`end_ts`, `local_start`/`local_end`, `civil_date` — the chart index and window queries |
| `raw_notifications.body` — zlib, then encrypted | `deleted_at`, `fetched_at`, `segment_type` |
| | all of `users` — its tokens are already encrypted by the token cipher |

The cost: an encrypted column cannot be filtered, indexed or aggregated in SQL.
Sums and averages move into Python in the read path. At one user that is
affordable — a month of heart-rate is about a million rows — and a cached daily
aggregate can be added later if a chart needs it. JSONB operators and any future
GIN index on `value`/`raw` are given up with it.

## Format

```
version (1 byte) ‖ nonce (12 bytes) ‖ ciphertext ‖ GCM tag (16 bytes)
```

- **The version byte** says which key and which encoding. Version 1 is the only
  one: one key, zlib-compressed JSON for the payload columns, uncompressed bytes
  for scalars. It exists so a future key rotation can read old rows with the old
  key; no rotation tooling is built until it is needed.
- **No associated data.** A ciphertext is not bound to its row, so an attacker
  with SQL *write* access could swap ciphertexts between rows undetected. The
  threat is reading, not tampering; binding is [deferred](decisions.md#deferred).
- **Compression is per column, not per row.** zlib on a three-byte scalar makes
  it bigger, so only the JSON columns compress.

## Storage

Encryption adds a fixed 29 bytes per value, yet the payload columns come out
**smaller** than today. JSONB is a binary format built for querying, not size —
a 4-byte header per key and value, offset tables, numbers as `numeric` structs —
and for small documents it is 30–40% larger than the same JSON as text. Encrypted
columns store compact JSON text, so the 29 bytes are outweighed by the JSONB
overhead they replace.

The exception is large payloads. Postgres compresses values over ~2 KB, and
ciphertext does not compress: a sleep session would grow from 2.5 KB to 16.8 KB.
Compressing before encrypting removes it. CRIME-style length leaks need an
attacker who mixes chosen input with the secret and observes the length; data at
rest offers no such oracle.

Measured on 2026-11-01 against the stored rows, `value` + `raw` per row, projected
to continuous operation (heart-rate ~34,000 samples a day dominates):

| | Plaintext JSONB | Encrypted | zlib + encrypted |
| --- | --- | --- | --- |
| heart-rate, per row | 760 B | 632 B | 463 B |
| steps / distance, per row | ~1,200 B | ~965 B | ~515 B |
| sleep, per row | 2,491 B | 16,820 B | 1,656 B |
| **payload columns, per year** | **≈ 10.6 GB** | **≈ 8.8 GB** | **≈ 6.2 GB** |

Structure columns and indexes add about 5 GB a year, unchanged by any of this.

## How it is wired

A **SQLAlchemy `TypeDecorator`** on the model columns, so model fields keep their
Python types (`Decimal`, `dict`) for mypy and the upsert needs no change — Core
`insert(...).on_conflict_do_update` passes bind parameters through the column
type. Three conditions keep it honest:

1. **The cipher is resolved lazily**, through `providers.get_data_cipher()` at
   bind and result time, never at import. The cipher class itself is an ordinary
   collaborator configured through `__init__`, constructible in a test without
   an environment. Settings are read only in wiring modules, as before.
2. **It is a recorded exception** to the SQLModel-only rule in
   [the stack](stack.md), alongside `JSONB` and `insert`.
3. **Reads select only the columns they use.** A transparent type decrypts
   whatever the ORM loads; loading whole rows would decompress and decrypt `raw`
   on every chart query.

An explicit cipher collaborator called at each write and read site was
considered and rejected: it turns model fields into `bytes` and every read site
into a place to forget a decrypt.

A minimal **read repository** — rows by `(user, data_type, civil_date range)`,
values decrypted — ships with the encryption, so the round trip is proven before
the read API routes are built on it.

## Proving it

- **Unit:** the cipher round-trips; both the compressed and the uncompressed
  path; the version byte is what it says.
- **Integration, against real Postgres:** upsert known fixtures, then read the
  raw rows with plain SQL, bypassing the models, and assert no known plaintext
  appears (`72`, `"beatsPerMinute"`, a stage name inside a payload), that each
  encrypted column is `bytea`, and that each carries the right compression flag.
  This is the test that catches a new column someone forgets to encrypt, and the
  compression path that only a large payload exercises.

## Cutover

No migrations (see [Alembic](decisions.md#open-decisions)), so a column type
changes the established way: drop the affected tables and let `create_all()`
recreate them. `create_all()` only creates what is missing, so `users` — and with
it the refresh token — survives, and no re-consent is needed.

- A CLI subcommand, **`db reset-measurements --force`**, drops the measurement
  tables and runs `create_all()`. Its table list comes from the measurement
  models, so `users` cannot be named. `--include-audit` also drops
  `raw_notifications`; it is needed this once, because `body` changes type.
  It will be reused for every schema change until migrations exist.
- Then `backfill run` from **2026-09-20**, the earliest stored day. Re-backfilling
  is a separate, explicit command.
- **`raw_notifications` history is lost** at this cutover. Acceptable during
  development only; after it, the audit log is not wiped.
