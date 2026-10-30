"""Asking Google for measurements.

Two things here are easy to get quietly wrong: the filter -- which is
type-prefixed and differs by structure, so a plausible-looking field name either
400s or narrows on the wrong thing -- and pagination, where stopping early loses
data silently.
"""

import datetime as dt

import pytest

from server.health.client import HealthDataClient, within
from server.health.error import FetchError, TokenExpiredError
from tests.google_data import interval_point
from tests.health.fakes import ExplodingTransport, FakeResponse, FakeTransport, page

START = dt.datetime(2026, 1, 2, tzinfo=dt.UTC)
END = dt.datetime(2026, 1, 3, tzinfo=dt.UTC)


def client_for(transport, retries=0):
    """A client that does not sleep: the backoff is asserted, never waited out."""
    return HealthDataClient(
        session=transport,  # type: ignore[arg-type]
        retries=retries,
        sleep=lambda _: None,
    )


def fetch_with_retries(transport, retries=3, data_type="steps"):
    return list(
        client_for(transport, retries=retries).list_data_points(
            access_token="token", data_type=data_type, start=START, end=END
        )
    )


def fetch(transport, data_type="steps"):
    return list(
        client_for(transport).list_data_points(
            access_token="token", data_type=data_type, start=START, end=END
        )
    )


# --- the request ---


def test_the_token_goes_in_the_authorization_header():
    transport = FakeTransport([page([])])

    fetch(transport)

    assert transport.requests[0]["headers"]["Authorization"] == "Bearer token"


def test_floor_rollup_requests_one_civil_day_with_a_bearer_token():
    transport = FakeTransport([FakeResponse(200, {"rollupDataPoints": []})])

    assert (
        client_for(transport).daily_floor_rollup(
            access_token="token", day=dt.date(2026, 1, 2)
        )
        == []
    )

    request = transport.requests[0]
    assert request["url"].endswith("/users/me/dataTypes/floors/dataPoints:dailyRollUp")
    assert request["headers"]["Authorization"] == "Bearer token"
    assert request["json"] == {
        "range": {
            "start": {"date": {"year": 2026, "month": 1, "day": 2}},
            "end": {"date": {"year": 2026, "month": 1, "day": 3}},
        },
        "windowSizeDays": 1,
    }


def test_floor_rollup_rejects_unexpected_pagination():
    transport = FakeTransport(
        [FakeResponse(200, {"rollupDataPoints": [], "nextPageToken": "more"})]
    )

    with pytest.raises(FetchError, match="more than one daily bucket"):
        client_for(transport).daily_floor_rollup(
            access_token="token", day=dt.date(2026, 1, 2)
        )


def test_floor_rollup_refuses_an_error_without_echoing_its_body():
    secret = "private floor measurement"
    transport = FakeTransport([FakeResponse(400, {"error": secret})])

    with pytest.raises(FetchError, match="400") as caught:
        client_for(transport).daily_floor_rollup(
            access_token="token", day=dt.date(2026, 1, 2)
        )

    assert secret not in str(caught.value)


def test_an_interval_type_filters_on_the_interval_start():
    transport = FakeTransport([page([])])

    fetch(transport, "steps")

    assert transport.requests[0]["params"]["filter"] == (
        'steps.interval.start_time >= "2026-01-02T00:00:00Z" '
        'AND steps.interval.start_time < "2026-01-03T00:00:00Z"'
    )


def test_a_sample_type_filters_on_the_sample_time():
    """A different field path entirely -- the reason the seed table exists."""
    transport = FakeTransport([page([])])

    fetch(transport, "weight")

    assert (
        "weight.sample_time.physical_time >="
        in transport.requests[0]["params"]["filter"]
    )


def test_an_unseeded_type_is_fetched_without_a_filter():
    """A guessed field name would be worse than none: wrong-but-valid silently
    narrows on the wrong thing, and we would never know."""
    transport = FakeTransport([page([])])

    fetch(transport, "brand_new_type")

    assert "filter" not in transport.requests[0]["params"]


def test_session_types_ask_for_the_smaller_page():
    """Google caps sessions at 25 and rejects a larger ask rather than clamping."""
    transport = FakeTransport([page([])])

    fetch(transport, "sleep")

    assert transport.requests[0]["params"]["pageSize"] == 25


def test_other_types_ask_for_the_larger_page():
    """5000, the live cap -- asking for 5000, 10000 or 20000 all return ~4996. The
    reference says 10000. At 1000 a day of heart-rate is 34 pages; at 5000 it is 7."""
    transport = FakeTransport([page([])])

    fetch(transport, "steps")

    assert transport.requests[0]["params"]["pageSize"] == 5000


# --- pagination ---


def test_every_page_is_followed():
    transport = FakeTransport(
        [
            page([interval_point(record_id="a")], next_token="p2"),
            page([interval_point(record_id="b")], next_token="p3"),
            page([interval_point(record_id="c")]),
        ]
    )

    points = fetch(transport)

    assert len(points) == 3
    assert transport.requests[1]["params"]["pageToken"] == "p2"


def test_pagination_stops_when_no_token_comes_back():
    transport = FakeTransport([page([interval_point()])])

    fetch(transport)

    assert len(transport.requests) == 1


def test_endless_pagination_is_refused():
    """A query that never stops paging is a bug, not a long day's walking. Looping
    against a rate limit forever is worse than failing."""
    transport = FakeTransport([page([interval_point()], next_token="more")] * 60)

    with pytest.raises(FetchError, match="did not stop paginating"):
        fetch(transport)


# --- failures ---


@pytest.mark.parametrize("status", [401, 403])
def test_a_rejected_token_is_its_own_error(status):
    """Distinct so the caller does not retry a credential that cannot work."""
    transport = FakeTransport([FakeResponse(status)])

    with pytest.raises(TokenExpiredError):
        fetch(transport)


def test_a_non_retryable_error_status_is_a_fetch_error():
    transport = FakeTransport([FakeResponse(400)])

    with pytest.raises(FetchError, match="400"):
        fetch(transport)


def test_an_error_body_is_never_logged_or_raised():
    """A 4xx from this endpoint can echo the filter, and the filter says which
    user's data was asked for over which window."""
    secret = 'steps.interval.start_time >= "2026-01-02" for 1234567890123456789'
    transport = FakeTransport([FakeResponse(400, {"error": {"message": secret}})])

    with pytest.raises(FetchError) as caught:
        fetch(transport)

    assert "1234567890123456789" not in str(caught.value)


def test_an_unreachable_api_is_a_fetch_error():
    with pytest.raises(FetchError, match="could not reach"):
        fetch(ExplodingTransport())


def test_a_non_json_answer_is_a_fetch_error():
    transport = FakeTransport([FakeResponse(200, None)])

    with pytest.raises(FetchError, match="not JSON"):
        fetch(transport)


def test_a_list_where_an_object_was_expected_is_a_fetch_error():
    transport = FakeTransport([FakeResponse(200, [])])

    with pytest.raises(FetchError, match="not an object"):
        fetch(transport)


def test_datapoints_that_is_not_a_list_is_a_fetch_error():
    """The shape of an answer is exactly what went wrong last time we assumed."""
    transport = FakeTransport([FakeResponse(200, {"dataPoints": {"oops": 1}})])

    with pytest.raises(FetchError, match="not a list"):
        fetch(transport)


def test_a_non_object_point_is_skipped_not_fatal():
    transport = FakeTransport(
        [FakeResponse(200, {"dataPoints": [interval_point(), "junk"]})]
    )

    assert len(fetch(transport)) == 1


# --- local narrowing, for unfiltered fetches ---


def test_a_point_inside_the_window_is_kept():
    assert within(dt.datetime(2026, 1, 2, 12, tzinfo=dt.UTC), START, END)


def test_a_point_outside_the_window_is_not():
    assert not within(dt.datetime(2026, 1, 5, tzinfo=dt.UTC), START, END)


def test_the_window_excludes_its_end():
    """Half-open, matching the filter, so consecutive days cannot double-count."""
    assert not within(END, START, END)


def test_a_point_with_no_time_is_kept():
    """Google is allowed to omit the physical interval; discarding those would
    lose full-day activities entirely."""
    assert within(None, START, END)


def test_a_daily_summary_is_narrowed_by_its_civil_date():
    assert within(None, START, END, dt.date(2026, 1, 2))
    assert within(None, START, END, dt.date(2026, 1, 1))
    assert not within(None, START, END, dt.date(2025, 12, 31))
    assert not within(None, START, END, dt.date(2026, 1, 5))


# --- throttling and transient failure ---


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_a_throttle_or_a_wobble_is_retried(status):
    """Observed live: heart-rate answered 503 partway through pagination. Failing
    outright discards the pages already fetched, and the limit is 300 requests a
    minute, which a high-frequency type reaches on its own."""
    transport = FakeTransport([FakeResponse(status), page([interval_point()])])

    assert len(fetch_with_retries(transport)) == 1
    assert len(transport.requests) == 2


def test_the_delay_doubles_between_attempts():
    recorded: list[float] = []
    transport = FakeTransport(
        [FakeResponse(503), FakeResponse(503), page([interval_point()])]
    )
    client = HealthDataClient(
        session=transport,  # type: ignore[arg-type]
        retries=3,
        sleep=recorded.append,
    )

    list(
        client.list_data_points(
            access_token="t", data_type="steps", start=START, end=END
        )
    )

    assert recorded == [1.0, 2.0]


def test_retries_eventually_give_up():
    """Better a clear failure than an unbounded wait: the message stays queued and
    the broker redelivers it in a minute anyway."""
    transport = FakeTransport([FakeResponse(503)] * 6)

    with pytest.raises(FetchError, match="503"):
        fetch_with_retries(transport, retries=2)


def test_an_unreachable_host_is_retried_then_reported():
    with pytest.raises(FetchError, match="could not reach"):
        list(
            HealthDataClient(
                session=ExplodingTransport(),  # type: ignore[arg-type]
                retries=2,
                sleep=lambda _: None,
            ).list_data_points(
                access_token="t", data_type="steps", start=START, end=END
            )
        )


def test_a_rejected_token_is_not_retried():
    """Retrying a credential that cannot work spends rate limit to learn nothing."""
    transport = FakeTransport([FakeResponse(401), page([interval_point()])])

    with pytest.raises(TokenExpiredError):
        fetch_with_retries(transport)
    assert len(transport.requests) == 1


# --- bounded paging for unfiltered types ---


def old_point(record_id="old"):
    """A point well before the window, as an unfiltered read walks backwards."""
    point = interval_point(
        "brand_new_type", record_id=record_id, payload_key="brand_new_type"
    )
    point["brand_new_type"]["interval"]["startTime"] = "2025-01-02T09:00:00Z"
    point["brand_new_type"]["interval"]["endTime"] = "2025-01-02T10:00:00Z"
    return point


def test_an_unfiltered_read_stops_once_it_is_past_the_window():
    """Results are newest first, so a page entirely before the window means
    everything after it is older still. Without this, one hour of heart-rate means
    paging through every point Google holds."""
    transport = FakeTransport(
        [
            page([old_point("a")], next_token="p2"),
            page([old_point("b")], next_token="p3"),
        ]
    )

    fetch(transport, "brand_new_type")

    assert len(transport.requests) == 1


def test_a_filtered_read_is_not_cut_short():
    """Google is already narrowing, so a page of older points means nothing."""
    transport = FakeTransport(
        [
            page([old_point("a")], next_token="p2"),
            page([interval_point(record_id="b")]),
        ]
    )

    fetch(transport, "steps")

    assert len(transport.requests) == 2


def test_a_page_with_no_readable_times_does_not_end_pagination():
    """Otherwise a point Google sent without a time would silently truncate the
    read and lose everything behind it."""
    transport = FakeTransport(
        [
            page(
                [{"name": "x", "brand_new_type": {"somethingNew": 1}}], next_token="p2"
            ),
            page([interval_point(record_id="b", payload_key="brand_new_type")]),
        ]
    )

    fetch(transport, "brand_new_type")

    assert len(transport.requests) == 2


def test_a_page_straddling_the_window_start_does_not_end_pagination():
    transport = FakeTransport(
        [
            page(
                [
                    old_point("a"),
                    interval_point(record_id="b", payload_key="brand_new_type"),
                ],
                next_token="p2",
            ),
            page([old_point("c")]),
        ]
    )

    fetch(transport, "brand_new_type")

    assert len(transport.requests) == 2


def daily_point(day: int, month: int = 1, year: int = 2026) -> dict:
    """Date-only Google summary, with no physical interval or sample time."""
    return {
        "dataSource": {"platform": "PLATFORM_ANDROID"},
        "dailyHeartRateZones": {
            "date": {"year": year, "month": month, "day": day},
            "zones": [],
        },
    }


def test_an_unfiltered_daily_summary_stops_at_an_older_date():
    transport = FakeTransport(
        [
            page([daily_point(2)], next_token="p2"),
            page([daily_point(31, 12, 2025)], next_token="p3"),
            page([daily_point(30, 12, 2025)], next_token="p4"),
        ]
    )

    points = fetch(transport, "daily-heart-rate-zones")

    assert len(points) == 2
    assert len(transport.requests) == 2


def test_a_daily_summary_just_before_the_utc_window_is_not_cut_off():
    transport = FakeTransport(
        [
            page([daily_point(1)], next_token="p2"),
            page([daily_point(2)]),
        ]
    )

    fetch(transport, "daily-heart-rate-zones")

    assert len(transport.requests) == 2


def test_an_unreadable_point_on_an_old_page_prevents_early_stop():
    transport = FakeTransport(
        [
            page(
                [daily_point(31, 12, 2025), {"unexpected": {"noDate": True}}],
                next_token="p2",
            ),
            page([daily_point(2)]),
        ]
    )

    fetch(transport, "daily-heart-rate-zones")

    assert len(transport.requests) == 2
