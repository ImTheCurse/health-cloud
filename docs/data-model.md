# Data model

Part of the [health-cloud design context](CONTEXT.md). What is stored, keyed on
what, and the three rules — idempotency, tombstones, civil time — that keep
reprocessing safe.

Subscribe to **all 29 data types** with the `AUTOMATIC` subscription policy
(Google creates subscriptions on consent; no per-user bookkeeping). Capture
wide, model narrow: display decisions come later, but data not subscribed to
today may be unrecoverable, since subscriptions do not backfill.

Tables:

- `users` — keyed on `healthUserId`, holds encrypted tokens, scopes, consent
  timestamps.
- `raw_notifications` — append-only audit log of every notification received.
  Never used to decide whether to fetch.
- `observation_time_intervals`, `observation_sample_times`,
  `session_time_intervals`, `session_segments`, `unknown_data_points` — the
  measurements. See *One table per shape* below.

### One table per shape, not per data type

Settled 2026-09-28, replacing an earlier plan for a single generic `data_points`
table. **A `DataPoint` carries exactly one of Google's three time structures**,
and that — not the data type's name — is what decides where it is stored:

| Google's structure | Table | Examples |
| --- | --- | --- |
| `ObservationTimeInterval` | `observation_time_intervals` | steps, distance, altitude |
| `ObservationSampleTime` | `observation_sample_times` | heart rate, weight, blood glucose |
| `SessionTimeInterval` | `session_time_intervals` | sleep, exercise, nutrition log |
| — (nested sub-intervals) | `session_segments` | sleep stages, laps, pause events |
| unrecognised or date-only | `unknown_data_points` | daily summaries, floor daily rollups, whatever Google adds next |

Three reasons this beats both alternatives it replaced:

- **Against one generic table:** the identity and time columns really are the
  same for every type, so they may as well be typed, indexed and queryable.
- **Against one table per data type:** no dataPoint payload has *ever* been
  fetched — a webhook delivers change pointers, not values — so 29 schemas would
  be 29 guesses from documentation, with no migrations to correct one. The documentation was already wrong once,
  about the webhook payload shape.
- **Routing is discoverable.** The structure is read off the payload, so a data
  type Google adds tomorrow lands somewhere sensible without a code change.
  `unknown_data_points` is not a fallback so much as the arrival gate every new
  type passes through before it is understood.

**There is a fourth shape.** A daily summary — `daily-resting-heart-rate` and its
siblings — carries a bare `date`, not an interval and not a sample time. This was
found on the first real run rather than designed for: the point landed in
`unknown_data_points` with its payload intact, which is precisely what that table
is for. Its `date` is read into `civil_date`, so the row is queryable by day
instead of being opaque, and it gets a table of its own only if a chart needs one.
Unfiltered reads narrow on that date, and the date is part of the derived record
id: summaries from different days must not overwrite each other on upsert.
`floors` cannot be read with `list`, so its `dailyRollUp` total uses this table
as well: `civil_date` is the returned day, `value_numeric` the `countSum`, and
`raw` the original rollup bucket. Its natural key is user, `floors`, all-sources,
and civil day. A missing bucket tombstones the old daily total.

One honest caveat: `SessionTimeInterval` and `ObservationTimeInterval` are
**field-identical**. A session is told apart by carrying sub-intervals, and where
it carries none, by a seed table of documented structures in
`server/health/const.py`. A segmentless session of an unseeded type is filed as
an interval — with its time and payload intact, so only the choice of table is
wrong.

### Columns every measurement shares

From step 6 every **value** column below — `value_numeric`, `value_unit`,
`value`, `raw` — is encrypted at rest, and the identity and time columns stay
plaintext so the key, the index and window queries still work. See
[Encryption at rest](encryption.md).

`health_user_id`, `data_type`, `record_id`, `start_ts`/`end_ts` (UTC, nullable),
`local_start`/`local_end` (no timezone), `civil_date`, `value_numeric` +
`value_unit`, `value` (the type-specific payload), `raw`, `deleted_at`,
`fetched_at`. A surrogate `id` primary key, with the natural key
`(health_user_id, data_type, record_id)` as a named unique constraint — the
`ON CONFLICT` target — and an index on `(health_user_id, data_type, civil_date)`,
which is the question every daily chart asks.

**What three tables cannot type is the value.** `steps.count` is an int64 in a
string, `heartRate.beatsPerMinute` an integer, a weight a quantity object with a
unit, a nutrition log a bag of nutrients. So a scalar is promoted to
`value_numeric`/`value_unit` when the payload has **exactly one** number, and the
union field is kept in `value` either way. Exactly one is the whole rule: a sleep
session carries both `minutesToFallAsleep` and `minutesAfterWakeup`, neither is
*the* measurement, and taking the first would put `12` in the column as though it
were the value of a night's sleep.

**`raw` is load-bearing, not defensive.** There are no migrations, and Google
serves only a few months of history (`list` returned steps from 120 days back and
none from 365, probed 2026-11-01), so a column modelled wrongly would otherwise
mean re-fetching data that may have aged out. With `raw`, a corrected model is
backfilled from our own database. It is `NOT NULL`, and the encrypted column
type keeps Python `None` as SQL NULL rather than encrypting it, so the constraint
bites and "no payload" stays distinguishable from "a payload that is null".

**Segments are their own table** because they are what a chart draws — a sleep
graph is the stages, not the session — and a JSONB array cannot be filtered by
stage or summed by duration without unnesting on every read. Google names them
per data type (`Sleep.SleepStage`, `Sleep.OutOfBedSegment`,
`Exercise.SplitSummary`, `Exercise.ExerciseEvent`) and has no umbrella term, so
the table is generic and `segment_type` carries Google's name. They are
**replaced** rather than upserted: a segment has no id of Google's own, so a
corrected session's stages must supersede the previous ones rather than
accumulate.

**Payload columns are encrypted `bytea`, not `jsonb`.** `value`, `raw`, the
segments' `value` and `raw_notifications.body` hold zlib-compressed, encrypted
JSON (see [Encryption at rest](encryption.md)), so JSON operators and GIN indexes
do not apply to them. Anything a query must filter on belongs in a plaintext
structure column.

### Idempotency

Delivery is at-least-once with 7 days of retries, so duplicates are certain.
Dedupe at the **data** level — always fetch, upsert on the natural key, let
reprocessing be a no-op.

Explicitly *not* at the notification level: a duplicate notification and a
genuine correction to the same interval are indistinguishable by payload hash,
so hashing would silently drop real edits. This is why JetStream's `Nats-Msg-Id`
deduplication is left switched off: a broker that offers the trap for free is
still offering the trap.

### Deletions

`operation: DELETE` **tombstones** (`deleted_at`) rather than removing the row.
Reads filter `deleted_at IS NULL`. A deletion that silently rewrites history
would produce unreproducible models once the ML work starts.

### Time

Two representations are stored, not three: the absolute UTC window
(`start_ts`/`end_ts`) and the user's wall clock (`local_start`/`local_end`), plus
`civil_date` derived from the local start. Google sends the absolute time
together with a `startUtcOffset`, so the local form is derived rather than parsed
— and `civilStartTime` is preferred when Google computed it itself.

The dashboard's daily aggregates key on the **civil date** — "my Tuesday step
count" means Tuesday where you were standing, not Tuesday in UTC. The local
columns are `timestamp without time zone` deliberately: the absence of an offset
is the point, and `timestamptz` would attach UTC and undo it.

Full-day activities omit `physicalTimeInterval` entirely, which is why the UTC
columns are nullable and `civil_date` is sometimes the only usable time. A change
pointer that carries only a civil interval has its fetch window **widened by 14
hours either side**, since reading a civil time as UTC can be a day's worth of
hours out: over-fetching costs a request, under-fetching loses a measurement.

### Fetch strategy

- **Hot path (webhook `UPSERT`):** `GET /v4/users/me/dataTypes/{type}/dataPoints`
  filtered to the notified interval. The notification already says exactly what
  changed, so this is the cheapest correct call.
- **Daily Prefect flow:** `:reconcile` over the trailing 7 days, as the safety
  net that catches what the webhook path missed or deleted.
