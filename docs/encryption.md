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
| `session_segments.label` — uncompressed; for a sleep stage, the label *is* the measurement | `deleted_at`, `fetched_at` |
| `session_segments.value` — zlib, then encrypted | `session_segments`: `session_id`, `segment_type` and its times |
| `raw_notifications.body` — zlib, then encrypted | `raw_notifications`: `received_at`, `request_id`, `pointer_count` |
| | all of `users` — its tokens are already encrypted by the token cipher |

The cost: an encrypted column cannot be filtered, indexed or aggregated in SQL.
Sums and averages move into Python in the read path. At one user that is
affordable — a month of heart-rate is about a million rows — and a cached daily
aggregate can be added later if a chart needs it. JSONB operators and any future
GIN index on `value`/`raw` are given up with it.

## Format

```
header (1 byte) ‖ nonce (12 bytes) ‖ ciphertext ‖ GCM tag (16 bytes)
```

- **The header byte** says which key and which encoding: the low seven bits are
  the key version, the high bit (`0x80`) is set when the plaintext was
  zlib-compressed. Key version 1 is the only one, so a stored value starts with
  `0x81` (JSON) or `0x01` (scalar). The version exists so a future key rotation
  can read old rows with the old key; no rotation tooling is built until it is
  needed.
- **The header is authenticated**, passed to GCM as associated data, so editing
  the compression flag or the key version fails to decrypt instead of misreading
  the value.
- **Nothing binds a ciphertext to its row.** An attacker with SQL *write* access
  could swap ciphertexts between rows undetected. The threat is reading, not
  tampering; binding is [deferred](decisions.md#deferred).
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

`DataCipher` in `server/crypto/data.py`, and `EncryptedJSON`,
`EncryptedDecimal` and `EncryptedText` in `server/models/encrypted.py`: a
**SQLAlchemy `TypeDecorator`** per kind of value on the model columns, so model fields keep their
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

**An encrypted column cannot be compared in SQL**: each encryption draws a fresh
nonce, so `WHERE value_unit = 'kg'` encrypts `'kg'` anew and matches nothing.
Filter on structure columns; compare values in Python.

A minimal **read repository**, `MeasurementRepository` in
`server/db/measurements.py` — measurements by `(user, data_type, civil_date
range)` with tombstones left out, and a session's segments — returns decrypted
values and never loads `raw`. The read API routes build on it.

## Proving it

- **Unit:** the cipher round-trips; both the compressed and the uncompressed
  path; the version byte is what it says.
- **Integration, against real Postgres**
  (`tests/integration/test_encryption_at_rest.py`): write a row to every table
  that holds health data, read it back with plain SQL that bypasses the models,
  and assert no known plaintext appears, each encrypted column is `bytea`, and
  each carries the right header. The test lists **every** column of those tables
  as either encrypted or structure, so a column added without that decision
  fails it rather than landing in plaintext.

## Changing a table's schema

No migrations (see [Alembic](decisions.md#open-decisions)), so a column type
changes by dropping the affected tables and letting `create_all()` recreate them.
`create_all()` only creates what is missing, so `users` — and with it the refresh
token — survives, and no re-consent is needed.

- **`uv run python -m server.cli db reset-measurements --force`** drops the
  measurement tables and recreates them empty. Its table list is fixed in the
  command, so `users` cannot be named; without `--force` it only says what it
  would drop. `--include-audit` also drops `raw_notifications`.
- Then **`backfill run`** refills them. It cannot refill everything: heart-rate
  accepts no time filter, so each day's window pages back from *now*, and the
  50-page cap stops it after roughly a week of heart-rate. Older heart-rate is
  lost by a reset — which is why the move to encryption did not use one.

## The move to encryption, 2026-11-01

The plaintext tables were rewritten in place rather than reset, because of that
heart-rate limit. A one-off script, after a `pg_dump`, read every row of the six
tables, dropped and recreated them, and wrote the rows back through the
encrypting column types — all in one transaction, since Postgres DDL is
transactional, and keeping the original ids so segments still found their
sessions. `users` was not touched. Nothing was lost, `raw_notifications`
included: 7,596 interval rows, 39,667 heart-rate samples, 2 sleep sessions with
74 segments, 23 daily summaries and 115 audit rows. A 3-day backfill then
topped up through the normal path.

Afterwards no heart-rate `raw` contained `beatsPerMinute`, every stored value
began with the expected header, and every row read back through
`MeasurementRepository`. The database went from 72 MB to 50 MB, though part of
that is the bloat a fresh table no longer carries.
