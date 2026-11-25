"""The unit of work: fetch an interval, write what came back.

Shared by the flow and the backfill CLI, so what it does with a pointer -- which
intervals it asks for, what it does with a DELETE, what it does when the window
cannot be read -- is the behaviour both inherit.
"""

import datetime as dt

import pytest

from server.health.client import HealthDataClient
from server.health.error import FetchError
from server.health.fetcher import Fetcher
from server.models.datapoint import (
    ObservationTimeInterval,
    SessionTimeInterval,
    UnknownDataPoint,
)
from server.models.user import User
from tests.google_data import (
    interval_point,
    live_daily_summary_point,
    live_exercise_point,
    sample_point,
    session_point,
)
from tests.google_webhook import FAKE_HEALTH_USER_ID
from tests.health.fakes import FakeResponse, FakeTransport, page

NOW = dt.datetime.now(dt.UTC)


class FakeTokens:
    def __init__(self, token: str = "token") -> None:
        self._token = token
        self.calls = 0

    def for_user(self, user) -> str:
        self.calls += 1
        return self._token


class RecordingSession:
    """Collects what would have been written, and when it was committed."""

    def __init__(self) -> None:
        self.added: list = []
        self.commits = 0
        self.upserted: list = []

    def commit(self) -> None:
        self.commits += 1

    def add(self, instance) -> None:
        self.added.append(instance)

    def execute(self, statement):  # pragma: no cover -- replace_segments' delete
        class Result:
            @staticmethod
            def scalar_one():
                return 1

        return Result()


def a_user() -> User:
    return User(
        health_user_id=FAKE_HEALTH_USER_ID,
        refresh_token_enc=b"x",
        granted_scopes="",
        consented_at=NOW,
        refreshed_at=NOW,
    )


def fetcher_over(transport, session=None):
    """A fetcher whose database writes are captured rather than performed.

    Returns its collaborators too, so a test asserts on them rather than reaching
    into the fetcher's attributes.
    """
    session = session or RecordingSession()
    tokens = FakeTokens()
    fetcher = Fetcher(
        HealthDataClient(session=transport),  # type: ignore[arg-type]
        tokens,  # type: ignore[arg-type]
        session,  # type: ignore[arg-type]
    )
    return fetcher, session, tokens


@pytest.fixture(autouse=True)
def captured_upserts(monkeypatch):
    """Records every row handed to either upsert path, without a database.

    Both are captured because the fetcher chooses between them: a session goes one
    at a time so its id comes back for the segments, and everything else goes in
    batches, because a day of heart-rate is 36,000 rows and one statement each is
    36,000 round trips.
    """
    rows: list = []

    def fake_upsert(session, point):
        rows.append(point)
        return len(rows)

    def fake_upsert_many(session, points):
        rows.extend(points)
        return len(points)

    segments: list = []

    def fake_replace(session, session_id, values):
        segments.append((session_id, values))

    monkeypatch.setattr("server.health.fetcher.upsert_data_point", fake_upsert)
    monkeypatch.setattr("server.health.fetcher.upsert_many", fake_upsert_many)
    monkeypatch.setattr("server.health.fetcher.replace_segments", fake_replace)
    return rows, segments


def an_interval(start="2026-01-02T09:00:00Z", end="2026-01-02T10:00:00Z"):
    return {"physicalTimeInterval": {"startTime": start, "endTime": end}}


def a_pointer(data_type="steps", operation="UPSERT", intervals=None):
    return {
        "dataType": data_type,
        "operation": operation,
        "healthUserId": FAKE_HEALTH_USER_ID,
        "intervals": intervals if intervals is not None else [an_interval()],
    }


# --- fetching an interval ---


def test_points_are_upserted(captured_upserts):
    rows, _ = captured_upserts
    fetcher, _, _tokens = fetcher_over(FakeTransport([page([interval_point()])]))

    result = fetcher.fetch_interval(
        user=a_user(),
        data_type="steps",
        start=dt.datetime(2026, 1, 2, tzinfo=dt.UTC),
        end=dt.datetime(2026, 1, 3, tzinfo=dt.UTC),
    )

    assert result.written == 1
    assert isinstance(rows[0], ObservationTimeInterval)


def test_one_commit_per_interval(captured_upserts):
    """A half-written window must not be half visible: either the interval landed
    or the message stays unacknowledged and it is fetched again."""
    fetcher, session, _tokens = fetcher_over(
        FakeTransport([page([interval_point(record_id=str(n)) for n in range(5)])])
    )

    fetcher.fetch_interval(
        user=a_user(),
        data_type="steps",
        start=dt.datetime(2026, 1, 2, tzinfo=dt.UTC),
        end=dt.datetime(2026, 1, 3, tzinfo=dt.UTC),
    )

    assert session.commits == 1


def test_a_session_also_writes_its_segments(captured_upserts):
    rows, segments = captured_upserts
    fetcher, _, _tokens = fetcher_over(FakeTransport([page([session_point()])]))

    result = fetcher.fetch_interval(
        user=a_user(),
        data_type="sleep",
        start=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
        end=dt.datetime(2026, 1, 3, tzinfo=dt.UTC),
    )

    assert isinstance(rows[0], SessionTimeInterval)
    assert result.segments == 3
    assert len(segments) == 1


def test_a_delete_tombstones(captured_upserts):
    rows, _ = captured_upserts
    fetcher, _, _tokens = fetcher_over(FakeTransport([page([interval_point()])]))

    fetcher.fetch_interval(
        user=a_user(),
        data_type="steps",
        start=dt.datetime(2026, 1, 2, tzinfo=dt.UTC),
        end=dt.datetime(2026, 1, 3, tzinfo=dt.UTC),
        deleted=True,
    )

    assert rows[0].deleted_at is not None


def floor_bucket(day=2, count="8"):
    return {
        "civilStartTime": {"date": {"year": 2026, "month": 1, "day": day}},
        "civilEndTime": {"date": {"year": 2026, "month": 1, "day": day + 1}},
        "floors": {"countSum": count},
    }


def floor_response(bucket):
    return FakeResponse(200, {"rollupDataPoints": [bucket]})


def test_floors_store_one_daily_total_and_preserve_the_rollup(captured_upserts):
    rows, _ = captured_upserts
    bucket = floor_bucket()
    fetcher, session, tokens = fetcher_over(FakeTransport([floor_response(bucket)]))

    result = fetcher.fetch_interval(
        user=a_user(),
        data_type="floors",
        start=dt.datetime(2026, 1, 2, 9, tzinfo=dt.UTC),
        end=dt.datetime(2026, 1, 2, 10, tzinfo=dt.UTC),
    )

    assert (result.written, result.unsupported) == (1, False)
    assert isinstance(rows[0], UnknownDataPoint)
    assert rows[0].civil_date == dt.date(2026, 1, 2)
    assert rows[0].value_numeric == 8
    assert rows[0].raw == bucket
    assert rows[0].record_id == "rollup:all-sources:2026-01-02"
    assert rows[0].source_platform == "GOOGLE_HEALTH"
    assert session.commits == 1
    assert tokens.calls == 1


def test_floors_delete_recomputes_the_daily_total(captured_upserts):
    rows, _ = captured_upserts
    fetcher, _, _ = fetcher_over(
        FakeTransport([floor_response(floor_bucket(count="3"))])
    )
    civil = {
        "civilIso8601TimeInterval": {
            "startTime": "2026-01-02T09:00:00",
            "endTime": "2026-01-02T10:00:00",
        }
    }

    results = fetcher.fetch_pointer(
        a_user(), a_pointer("floors", operation="DELETE", intervals=[civil])
    )

    assert results[0].written == 1
    assert rows[0].value_numeric == 3
    assert rows[0].deleted_at is None


def test_floors_use_the_notified_civil_day_not_the_utc_day(captured_upserts):
    rows, _ = captured_upserts
    fetcher, _, _ = fetcher_over(FakeTransport([floor_response(floor_bucket())]))
    interval = {
        "physicalTimeInterval": {
            "startTime": "2026-01-03T02:00:00Z",
            "endTime": "2026-01-03T03:00:00Z",
        },
        "civilIso8601TimeInterval": {
            "startTime": "2026-01-02T21:00:00",
            "endTime": "2026-01-02T22:00:00",
        },
    }

    fetcher.fetch_pointer(a_user(), a_pointer("floors", intervals=[interval]))

    assert rows[0].civil_date == dt.date(2026, 1, 2)


def test_empty_floor_rollup_tombstones_a_stale_total(captured_upserts):
    fetcher, session, _ = fetcher_over(
        FakeTransport([FakeResponse(200, {"rollupDataPoints": []})])
    )
    stale = UnknownDataPoint(
        health_user_id=a_user().health_user_id,
        data_type="floors",
        record_id="rollup:all-sources:2026-01-02",
        civil_date=dt.date(2026, 1, 2),
        raw=floor_bucket(),
        fetched_at=NOW,
    )

    class ExistingResult:
        def first(self):
            return stale

    session.exec = lambda _: ExistingResult()
    fetcher.fetch_interval(
        user=a_user(),
        data_type="floors",
        start=dt.datetime(2026, 1, 2, tzinfo=dt.UTC),
        end=dt.datetime(2026, 1, 3, tzinfo=dt.UTC),
    )

    assert stale.deleted_at is not None
    assert session.commits == 1


def test_floors_reject_a_rollup_for_a_different_day(captured_upserts):
    fetcher, session, _ = fetcher_over(
        FakeTransport([floor_response(floor_bucket(day=3))])
    )

    with pytest.raises(FetchError, match="unexpected civil day"):
        fetcher.fetch_interval(
            user=a_user(),
            data_type="floors",
            start=dt.datetime(2026, 1, 2, tzinfo=dt.UTC),
            end=dt.datetime(2026, 1, 3, tzinfo=dt.UTC),
        )
    assert session.commits == 0


def test_a_point_outside_the_window_is_not_written(captured_upserts):
    """Only reachable for an unseeded type, which is fetched unfiltered."""
    rows, _ = captured_upserts
    point = interval_point("brand_new_type", payload_key="brand_new_type")
    fetcher, _, _tokens = fetcher_over(FakeTransport([page([point])]))

    result = fetcher.fetch_interval(
        user=a_user(),
        data_type="brand_new_type",
        start=dt.datetime(2026, 5, 1, tzinfo=dt.UTC),
        end=dt.datetime(2026, 5, 2, tzinfo=dt.UTC),
    )

    assert (result.written, result.skipped) == (0, 1)
    assert rows == []


def test_a_session_that_began_before_the_window_is_written(captured_upserts):
    """A notification can name a window that starts partway through a session,
    as a workout's mid-session updates do. The session overlaps the window, so it
    is the data the notification is about."""
    rows, _ = captured_upserts
    fetcher, _, _ = fetcher_over(FakeTransport([page([session_point()])]))

    result = fetcher.fetch_interval(
        user=a_user(),
        data_type="sleep",
        start=dt.datetime(2026, 1, 2, tzinfo=dt.UTC),
        end=dt.datetime(2026, 1, 2, 12, tzinfo=dt.UTC),
    )

    assert (result.written, result.skipped) == (1, 0)
    assert len(rows) == 1


# --- the workout of 2026-11-25, as Google listed it and notified about it ---

#: The session as Google lists it once finished.
WORKOUT_START = "2026-11-25T04:16:06Z"
WORKOUT_END = "2026-11-25T04:46:27Z"
#: The session before it, which was the newest Google listed during the workout.
PREVIOUS_START = "2026-11-24T18:50:46Z"
PREVIOUS_END = "2026-11-24T19:20:54Z"
#: The two windows Google notified while the workout was running. Both start
#: when the workout did, and both end before it finished.
FIRST_NOTIFIED = (
    dt.datetime(2026, 11, 25, 4, 16, 6, tzinfo=dt.UTC),
    dt.datetime(2026, 11, 25, 4, 16, 11, 90717, tzinfo=dt.UTC),
)
SECOND_NOTIFIED = (
    dt.datetime(2026, 11, 25, 4, 16, 6, tzinfo=dt.UTC),
    dt.datetime(2026, 11, 25, 4, 31, 23, 646710, tzinfo=dt.UTC),
)


def fetch_exercise(points, window):
    fetcher, _, _ = fetcher_over(FakeTransport([page(points)]))
    start, end = window
    return fetcher.fetch_interval(
        user=a_user(), data_type="exercise", start=start, end=end
    )


@pytest.mark.parametrize("window", [FIRST_NOTIFIED, SECOND_NOTIFIED])
def test_the_listed_workout_is_kept_for_either_notified_window(
    captured_upserts, window
):
    """Each notified window covers only part of the session, which runs on past
    the window's end. Listed, the session is written."""
    rows, _ = captured_upserts

    result = fetch_exercise(
        [
            live_exercise_point(WORKOUT_START, WORKOUT_END),
            live_exercise_point(PREVIOUS_START, PREVIOUS_END),
        ],
        window,
    )

    assert (result.written, result.skipped) == (1, 1)
    assert rows[0].start_ts == dt.datetime(2026, 11, 25, 4, 16, 6, tzinfo=dt.UTC)


@pytest.mark.parametrize("window", [FIRST_NOTIFIED, SECOND_NOTIFIED])
def test_a_workout_google_does_not_list_yet_cannot_be_kept(captured_upserts, window):
    """What the server saw during the workout: Google's newest session was the
    one before it, so nothing was written. Only a fetch after the session is
    listed can store it, which a notification-driven fetch never makes."""
    rows, _ = captured_upserts

    result = fetch_exercise(
        [live_exercise_point(PREVIOUS_START, PREVIOUS_END)], window
    )

    assert (result.written, result.skipped) == (0, 1)
    assert rows == []


def test_the_workout_is_kept_by_a_fetch_after_it_is_listed(captured_upserts):
    """A fetch over the morning, after Google listed the finished session, the
    way a scheduled backfill would."""
    rows, _ = captured_upserts

    result = fetch_exercise(
        [
            live_exercise_point(WORKOUT_START, WORKOUT_END),
            live_exercise_point(PREVIOUS_START, PREVIOUS_END),
        ],
        (
            dt.datetime(2026, 11, 25, 4, tzinfo=dt.UTC),
            dt.datetime(2026, 11, 25, 5, tzinfo=dt.UTC),
        ),
    )

    assert (result.written, result.skipped) == (1, 1)
    assert len(rows) == 1


def test_a_daily_summary_outside_the_window_is_not_written(captured_upserts):
    rows, _ = captured_upserts
    fetcher, session, _ = fetcher_over(
        FakeTransport([page([live_daily_summary_point()])])
    )

    result = fetcher.fetch_interval(
        user=a_user(),
        data_type="daily-resting-heart-rate",
        start=dt.datetime(2026, 5, 1, tzinfo=dt.UTC),
        end=dt.datetime(2026, 5, 2, tzinfo=dt.UTC),
    )

    assert (result.written, result.skipped) == (0, 1)
    assert rows == []
    assert session.commits == 1


def test_a_daily_summary_in_the_window_is_written(captured_upserts):
    rows, _ = captured_upserts
    fetcher, _, _ = fetcher_over(FakeTransport([page([live_daily_summary_point()])]))

    result = fetcher.fetch_interval(
        user=a_user(),
        data_type="daily-resting-heart-rate",
        start=dt.datetime(2026, 1, 2, tzinfo=dt.UTC),
        end=dt.datetime(2026, 1, 3, tzinfo=dt.UTC),
    )

    assert result.written == 1
    assert rows[0].civil_date == dt.date(2026, 1, 2)


# --- fetching what a pointer describes ---


def test_every_interval_in_a_pointer_is_fetched(captured_upserts):
    """Google batches intervals as well as pointers."""
    fetcher, _, _tokens = fetcher_over(
        FakeTransport([page([interval_point()]), page([interval_point()])])
    )

    results = fetcher.fetch_pointer(
        a_user(),
        a_pointer(
            intervals=[
                an_interval(),
                an_interval("2026-01-03T09:00:00Z", "2026-01-03T10:00:00Z"),
            ]
        ),
    )

    assert len(results) == 2


def test_a_pointer_with_no_intervals_does_nothing(captured_upserts):
    rows, _ = captured_upserts
    fetcher, _, _tokens = fetcher_over(FakeTransport())

    assert fetcher.fetch_pointer(a_user(), a_pointer(intervals=[])) == []
    assert rows == []


def test_an_unreadable_interval_is_refused_not_skipped(captured_upserts):
    """Skipping would silently lose the measurement the notification was about."""
    fetcher, _, _tokens = fetcher_over(FakeTransport())

    with pytest.raises(FetchError, match="unreadable interval"):
        fetcher.fetch_pointer(a_user(), a_pointer(intervals=[{"nothing": "useful"}]))


def test_a_full_day_pointer_widens_the_window(captured_upserts):
    """A civil interval read as UTC can be a day's worth of hours out at the
    edges, so the window is widened rather than risking a miss. Over-fetching
    costs a request; under-fetching loses a measurement.

    Asserted on the filter Google was actually sent, which is the only place the
    widening is observable.
    """
    transport = FakeTransport([page([])])
    fetcher, _, _tokens = fetcher_over(transport)

    fetcher.fetch_pointer(
        a_user(),
        a_pointer(
            intervals=[
                {
                    "civilIso8601TimeInterval": {
                        "startTime": "2026-01-02T00:00:00",
                        "endTime": "2026-01-03T00:00:00",
                    }
                }
            ]
        ),
    )

    sent = transport.requests[0]["params"]["filter"]
    assert '>= "2026-01-01T10:00:00Z"' in sent
    assert '< "2026-01-03T14:00:00Z"' in sent


def test_a_pointer_with_a_physical_interval_is_not_widened(captured_upserts):
    """The widening is a concession to a missing physical interval, not a habit."""
    transport = FakeTransport([page([])])
    fetcher, _, _tokens = fetcher_over(transport)

    fetcher.fetch_pointer(a_user(), a_pointer())

    sent = transport.requests[0]["params"]["filter"]
    assert '>= "2026-01-02T09:00:00Z"' in sent
    assert '< "2026-01-02T10:00:00Z"' in sent


def test_the_token_is_fetched_once_per_interval(captured_upserts):
    """Not once per point: a refresh is an HTTP call, and the token is good for
    the whole interval."""
    fetcher, _, tokens = fetcher_over(
        FakeTransport([page([interval_point(record_id=str(n)) for n in range(3)])])
    )

    fetcher.fetch_interval(
        user=a_user(),
        data_type="steps",
        start=dt.datetime(2026, 1, 2, tzinfo=dt.UTC),
        end=dt.datetime(2026, 1, 3, tzinfo=dt.UTC),
    )

    assert tokens.calls == 1


def test_the_raw_user_id_never_reaches_the_log(captured_upserts, logs):
    fetcher, _, _tokens = fetcher_over(FakeTransport([page([interval_point()])]))
    user = a_user()

    fetcher.fetch_interval(
        user=user,
        data_type="steps",
        start=dt.datetime(2026, 1, 2, tzinfo=dt.UTC),
        end=dt.datetime(2026, 1, 3, tzinfo=dt.UTC),
    )

    assert logs, "nothing was logged, so this would pass vacuously"
    assert user.health_user_id not in str([r.record["message"] for r in logs])


def test_rows_are_batched_rather_than_written_one_at_a_time(
    captured_upserts, monkeypatch
):
    """A day of heart-rate is ~36,000 points. One statement each is 36,000 round
    trips, which is slow enough to outrun the consumer's ack_wait and get the
    message redelivered underneath the run that is still working on it."""
    batches: list[int] = []

    def counting_upsert_many(session, points):
        batches.append(len(points))
        return len(points)

    monkeypatch.setattr("server.health.fetcher.upsert_many", counting_upsert_many)
    fetcher, _, _tokens = fetcher_over(
        FakeTransport([page([interval_point(record_id=str(n)) for n in range(1200)])])
    )

    fetcher.fetch_interval(
        user=a_user(),
        data_type="steps",
        start=dt.datetime(2026, 1, 2, tzinfo=dt.UTC),
        end=dt.datetime(2026, 1, 3, tzinfo=dt.UTC),
    )

    # 500 + 500 + the 200 left over when the pages run out.
    assert batches == [500, 500, 200]


def test_a_session_is_still_written_one_at_a_time(captured_upserts):
    """It needs its id back so the segments have a parent to point at."""
    rows, segments = captured_upserts
    fetcher, _, _tokens = fetcher_over(FakeTransport([page([session_point()])]))

    fetcher.fetch_interval(
        user=a_user(),
        data_type="sleep",
        start=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
        end=dt.datetime(2026, 1, 3, tzinfo=dt.UTC),
    )

    assert len(segments) == 1


# --- backfilling a window in one pass ---


def heart_rate_at(moment: str, record_id: str) -> dict:
    """A heart-rate sample at ``moment``, for walking a pass across days."""
    point = sample_point(data_type="heart-rate", record_id=record_id)
    point["heart-rate"]["sampleTime"]["physicalTime"] = moment
    return point


def backfill(fetcher, start=(2026, 1, 1), end=(2026, 1, 4), on_day=None):
    return fetcher.backfill_window(
        user=a_user(),
        data_type="heart-rate",
        start=dt.datetime(*start, tzinfo=dt.UTC),
        end=dt.datetime(*end, tzinfo=dt.UTC),
        on_day=on_day,
    )


def test_a_backfill_commits_each_day_as_the_pass_leaves_it(captured_upserts):
    """Newest first, across three days and two pages: every day lands, each in
    its own commit, so a run that dies halfway keeps the days it finished."""
    rows, _ = captured_upserts
    transport = FakeTransport(
        [
            page(
                [
                    heart_rate_at("2026-01-03T20:00:00Z", "c2"),
                    heart_rate_at("2026-01-03T08:00:00Z", "c1"),
                    heart_rate_at("2026-01-02T22:00:00Z", "b2"),
                ],
                next_token="more",
            ),
            page(
                [
                    heart_rate_at("2026-01-02T01:00:00Z", "b1"),
                    heart_rate_at("2026-01-01T12:00:00Z", "a1"),
                ]
            ),
        ]
    )
    fetcher, session, _tokens = fetcher_over(transport)
    days: list[tuple[dt.date, int]] = []

    result = backfill(fetcher, on_day=lambda day, n: days.append((day, n)))

    assert result.written == 5
    assert [row.record_id for row in rows] == ["c2", "c1", "b2", "b1", "a1"]
    assert days == [
        (dt.date(2026, 1, 3), 2),
        (dt.date(2026, 1, 2), 2),
        (dt.date(2026, 1, 1), 1),
    ]
    assert session.commits == 3


def test_a_backfill_makes_one_request_per_page_not_per_day(captured_upserts):
    """The point of the single pass: day-by-day re-reads every newer page for
    each older day."""
    transport = FakeTransport(
        [
            page([heart_rate_at("2026-01-03T10:00:00Z", "c")], next_token="p2"),
            page([heart_rate_at("2026-01-02T10:00:00Z", "b")], next_token="p3"),
            page([heart_rate_at("2026-01-01T10:00:00Z", "a")]),
        ]
    )
    fetcher, _, _tokens = fetcher_over(transport)

    backfill(fetcher)

    assert len(transport.requests) == 3
    assert "filter" not in transport.requests[0]["params"]


def test_a_backfill_stops_once_a_page_is_older_than_the_window(captured_upserts):
    rows, _ = captured_upserts
    transport = FakeTransport(
        [
            page([heart_rate_at("2026-01-02T10:00:00Z", "in")], next_token="p2"),
            page([heart_rate_at("2025-12-30T10:00:00Z", "old")], next_token="p3"),
            page([heart_rate_at("2025-12-29T10:00:00Z", "older")]),
        ]
    )
    fetcher, _, _tokens = fetcher_over(transport)

    result = backfill(fetcher)

    assert [row.record_id for row in rows] == ["in"]
    assert result.skipped == 1
    assert len(transport.requests) == 2


def test_a_backfill_asks_for_the_token_before_every_page(captured_upserts):
    """A 90-day pass of heart-rate runs for over an hour; one token fetched at the
    start would expire partway through."""
    transport = FakeTransport(
        [
            page([heart_rate_at("2026-01-03T10:00:00Z", "c")], next_token="p2"),
            page([heart_rate_at("2026-01-02T10:00:00Z", "b")], next_token="p3"),
            page([heart_rate_at("2026-01-01T10:00:00Z", "a")]),
        ]
    )
    fetcher, _, tokens = fetcher_over(transport)

    backfill(fetcher)

    assert tokens.calls == 3


def test_a_backfill_page_limit_grows_with_the_window(captured_upserts):
    """One day of heart-rate is ~7 pages, so the flat per-interval limit of 50
    would stop a long pass after about a week."""
    endless = [
        page([heart_rate_at("2026-01-03T10:00:00Z", str(n))], next_token=str(n))
        for n in range(80)
    ]
    fetcher, _, _tokens = fetcher_over(FakeTransport(endless))

    # Three days allow 150 pages, so 80 is fine where 50 would have raised.
    backfill(fetcher)


def test_a_backfill_still_refuses_a_runaway_pass(captured_upserts):
    endless = [
        page([heart_rate_at("2026-01-01T10:00:00Z", str(n))], next_token=str(n))
        for n in range(60)
    ]
    fetcher, _, _tokens = fetcher_over(FakeTransport(endless))

    with pytest.raises(FetchError):
        backfill(fetcher, start=(2026, 1, 1), end=(2026, 1, 2))


def test_a_backfill_of_an_unreadable_type_does_nothing(captured_upserts):
    fetcher, _, tokens = fetcher_over(FakeTransport())

    result = fetcher.backfill_window(
        user=a_user(),
        data_type="total-calories",
        start=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
        end=dt.datetime(2026, 1, 2, tzinfo=dt.UTC),
    )

    assert result.unsupported
    assert tokens.calls == 0


# --- the hours the heart-rate summaries must rebuild ---


def test_a_rolled_up_type_reports_the_local_hours_it_wrote(captured_upserts):
    """The rollup run needs to know which hours to rebuild, on the user's clock:
    the point starts at 09:00 UTC with a -4h offset, so 05:00 local."""
    fetcher, _, _ = fetcher_over(
        FakeTransport([page([interval_point(data_type="time-in-heart-rate-zone")])])
    )

    result = fetcher.fetch_interval(
        user=a_user(),
        data_type="time-in-heart-rate-zone",
        start=dt.datetime(2026, 1, 2, tzinfo=dt.UTC),
        end=dt.datetime(2026, 1, 3, tzinfo=dt.UTC),
    )

    assert result.hours is not None
    assert (result.hours.start, result.hours.end) == (
        dt.datetime(2026, 1, 2, 5),
        dt.datetime(2026, 1, 2, 6),
    )


def test_any_other_type_reports_no_hours(captured_upserts):
    fetcher, _, _ = fetcher_over(FakeTransport([page([interval_point()])]))

    result = fetcher.fetch_interval(
        user=a_user(),
        data_type="steps",
        start=dt.datetime(2026, 1, 2, tzinfo=dt.UTC),
        end=dt.datetime(2026, 1, 3, tzinfo=dt.UTC),
    )

    assert result.written == 1
    assert result.hours is None


def test_nothing_written_reports_no_hours(captured_upserts):
    fetcher, _, _ = fetcher_over(FakeTransport([page([])]))

    result = fetcher.fetch_interval(
        user=a_user(),
        data_type="heart-rate",
        start=dt.datetime(2026, 1, 2, tzinfo=dt.UTC),
        end=dt.datetime(2026, 1, 3, tzinfo=dt.UTC),
    )

    assert result.hours is None
