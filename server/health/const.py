"""Constants for reading measurements out of the Health API."""

from typing import Final

from server.models.const import TimeStructure

#: The data API. Subscriber management lives on the same host but is a
#: project-level API authorised differently -- see ``server.webhooks.subscriber``.
API_ROOT: Final = "https://health.googleapis.com/v4"

#: Google's OAuth token endpoint, for exchanging a refresh token.
TOKEN_URI: Final = "https://oauth2.googleapis.com/token"

#: Points per page. The reference says the maximum is 10000; the live API caps it
#: at roughly 5000 -- asking for 5000, 10000 or 20000 all return the same ~4996
#: (verified 2026-09-28). Asking for the real cap rather than the documented one
#: matters: heart-rate produces ~34,000 points a day, which is 7 pages at this size
#: and 34 at the 1000 this started as.
#:
#: Session types cap at 25 instead, and reject a larger ask rather than clamping.
PAGE_SIZE: Final = 5000
SESSION_PAGE_SIZE: Final = 25

#: Stop paging. A single interval returning this many pages means something is
#: wrong with the query, not that the user walked that much; failing loudly beats
#: looping against a rate limit.
MAX_PAGES: Final = 50

#: Google returns dataPoints **newest first** -- verified live 2026-09-28, by
#: paging heart-rate and comparing the first and last timestamps.
#:
#: Load-bearing for unfiltered types. Without a filter the first page starts at
#: "now", so once a page's points are older than the window being asked for,
#: everything after it is older still and there is nothing left to find. Stopping
#: there turns an unbounded walk through all history into a read bounded by the
#: window.
#:
#: The number that made this necessary: heart-rate produces roughly 1,400 points
#: an hour, so a 7-day window is around 235,000 points and 235 pages. Fetching
#: that to keep one hour of it is what earned a 503 from Google.
RESULTS_ARE_NEWEST_FIRST: Final = True

#: Retries for a transient refusal, with the delay doubling each time. 429 and 5xx
#: are the documented shapes of "too fast" and "not now": the rate limit is 300
#: requests a minute per user, and a paginated read of a high-frequency type gets
#: there easily.
FETCH_RETRIES: Final = 3
RETRY_BASE_DELAY_SECONDS: Final = 1.0

#: Statuses worth trying again. 429 is throttling; 5xx is Google's side.
RETRYABLE_STATUSES: Final[frozenset[int]] = frozenset({429, 500, 502, 503, 504})

#: Refresh the access token when it expires within this long. Google's are good
#: for about an hour, and a fetch must not begin with a credential that dies
#: mid-pagination.
EXPIRY_MARGIN_SECONDS: Final = 300

#: The filter field each data type actually accepts, verified against the live
#: API on 2026-09-28 by trying every candidate spelling and keeping what returned
#: 200.
#:
#: Not derivable from the structure, which is why this is a per-type table rather
#: than the three-entry one it started as. ``sleep`` is a session and filters on
#: ``interval.end_time``; ``steps`` is an interval and filters on
#: ``interval.start_time``; ``heart-rate`` is a sample and accepts **no** filter
#: field at all. The reference does not say this and got it wrong for sleep.
#:
#: A type absent here is fetched unfiltered and narrowed locally. That is the
#: deliberate default rather than a gap: a guessed field name is a 400 at best,
#: and at worst a valid field that silently filters on the wrong thing.
FILTER_FIELDS: Final[dict[str, str]] = {
    "steps": "interval.start_time",
    "distance": "interval.start_time",
    "altitude": "interval.start_time",
    "sleep": "interval.end_time",
    "weight": "sample_time.physical_time",
}

#: Data type ids are **kebab-case**: ``heart-rate``, not ``heart_rate`` or
#: ``heartRate``. Both of those are rejected as "Invalid data type ID", and the
#: reference uses camelCase in one place and kebab-case in another. Verified live,
#: 2026-09-28.
#:
#: Which structure each type carries, used for two things:
#:
#: 1. Page size. Session types cap at 25 and reject a larger ask rather than
#:    clamping it.
#: 2. Telling a session from an interval. ``SessionTimeInterval`` and
#:    ``ObservationTimeInterval`` are *field-identical*, so nothing in a payload
#:    distinguishes them except the presence of sub-intervals. Where a session
#:    carries segments the payload still wins; where it carries none, this is the
#:    only signal.
#:
#: A sample is always identified from the payload, and so is an unrecognised
#: shape, so a type absent from here is never misrouted into the wrong *kind* of
#: table -- at worst a segmentless session is filed as an interval, with its time
#: and payload intact.
SEED_STRUCTURES: Final[dict[str, TimeStructure]] = {
    # ObservationTimeInterval -- accumulated over a window.
    "steps": TimeStructure.INTERVAL,
    "distance": TimeStructure.INTERVAL,
    "altitude": TimeStructure.INTERVAL,
    "active-minutes": TimeStructure.INTERVAL,
    "active-zone-minutes": TimeStructure.INTERVAL,
    "activity-level": TimeStructure.INTERVAL,
    "sedentary-period": TimeStructure.INTERVAL,
    "active-energy-burned": TimeStructure.INTERVAL,
    "time-in-heart-rate-zone": TimeStructure.INTERVAL,
    "swim-lengths-data": TimeStructure.INTERVAL,
    # ObservationSampleTime -- measured at an instant.
    "heart-rate": TimeStructure.SAMPLE,
    "heart-rate-variability": TimeStructure.SAMPLE,
    "oxygen-saturation": TimeStructure.SAMPLE,
    "body-fat": TimeStructure.SAMPLE,
    "blood-glucose": TimeStructure.SAMPLE,
    "core-body-temperature": TimeStructure.SAMPLE,
    "weight": TimeStructure.SAMPLE,
    "vo2-max": TimeStructure.SAMPLE,
    "daily-resting-heart-rate": TimeStructure.SAMPLE,
    "daily-heart-rate-variability": TimeStructure.SAMPLE,
    "daily-oxygen-saturation": TimeStructure.SAMPLE,
    "daily-respiratory-rate": TimeStructure.SAMPLE,
    "daily-vo2-max": TimeStructure.SAMPLE,
    "daily-heart-rate-zones": TimeStructure.SAMPLE,
    # SessionTimeInterval -- a window bundling metrics and sub-intervals.
    "sleep": TimeStructure.SESSION,
    "exercise": TimeStructure.SESSION,
    "nutrition-log": TimeStructure.SESSION,
    "hydration-log": TimeStructure.SESSION,
    "food": TimeStructure.SESSION,
    "electrocardiogram": TimeStructure.SESSION,
    "irregular-rhythm-notification": TimeStructure.SESSION,
}

#: Types that exist but whose measurements cannot be read with ``list``.
#: Verified live, 2026-09-28 -- the API answers "List is not supported for data
#: type X, but the following actions are supported: ...".
#:
#: Two groups, for different reasons:
#:
#: - ``floors``, ``total-calories`` and ``calories-in-heart-rate-zone`` are
#:   read through ``rollUp``/``dailyRollUp`` instead. ``floors`` now has its own
#:   daily rollup path in the fetcher, but still cannot be read with ``list``.
#:   The other two are acknowledged with a warning and not collected yet.
#: - ``menstrual-period``, ``moods``, ``ovulation-test`` and ``symptoms`` support
#:   only ``create``/``update``/``batchDelete``. They are user-entered and there is
#:   nothing to read, so nothing is missing.
LIST_UNSUPPORTED: Final[frozenset[str]] = frozenset(
    {
        "floors",
        "total-calories",
        "calories-in-heart-rate-zone",
        "menstrual-period",
        "moods",
        "ovulation-test",
        "symptoms",
    }
)

#: Payload keys that identify a structure when the response is read back. These
#: are what actually decide the table.
INTERVAL_KEY: Final = "interval"
SAMPLE_TIME_KEY: Final = "sampleTime"
START_TIME_KEY: Final = "startTime"
END_TIME_KEY: Final = "endTime"
PHYSICAL_TIME_KEY: Final = "physicalTime"

#: Nested arrays inside a session, and the segment type each produces.
SEGMENT_KEYS: Final[tuple[str, ...]] = (
    "stages",
    "shortAwakenings",
    "outOfBedSegments",
    "splits",
    "events",
)

#: Rows sent to Postgres per statement. Large enough that a day of a
#: high-frequency type is a handful of statements rather than tens of thousands,
#: small enough that one statement's parameter list stays sane.
UPSERT_BATCH_SIZE: Final = 500
