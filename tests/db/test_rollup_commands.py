"""The CLI's side of the hourly heart-rate summaries.

A backfill of heart rate must end with a rollup run, since nothing else would
rebuild the hours it wrote; ``rollup rebuild`` is the manual path. Neither needs
a database here: the fetch, the user lookup and the rebuild are replaced.
"""

import datetime as dt

import pytest

from server import cli
from server.health.error import HealthApiError
from server.orchestration.error import TriggerError


class FakeUser:
    health_user_id = "fake-user"


class FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def offline(monkeypatch):
    """The backfill with every fetch a no-op, and the rollup runs it asked for."""
    monkeypatch.setattr(cli, "get_session", FakeSession)
    monkeypatch.setattr(cli, "_only_user", lambda requested, session: FakeUser())
    monkeypatch.setattr(cli, "build_fetcher", lambda session: None)
    monkeypatch.setattr(cli, "backfill_type", lambda *args, **kwargs: None)

    runs: list[dict] = []

    class Trigger:
        def trigger(self, parameters=None):
            runs.append(parameters)
            return "run-1"

    monkeypatch.setattr(
        cli.FlowTrigger, "by_name", classmethod(lambda cls, url, name: Trigger())
    )
    return runs


def run(*argv: str) -> None:
    args = cli.build_parser().parse_args(list(argv))
    args.handler(args)


def test_a_heart_rate_backfill_ends_with_a_rollup_run(offline):
    run("backfill", "run", "--types", "heart-rate", "--days", "2", "--until", "2026-01-10")

    [parameters] = offline
    assert parameters["health_user_id"] == "fake-user"
    # Two UTC days, widened by the furthest a local clock can be from UTC.
    assert parameters["start"] == "2026-01-07T10:00:00"
    assert parameters["end"] == "2026-01-10T15:00:00"


def test_a_backfill_without_heart_rate_asks_for_no_run(offline):
    run("backfill", "run", "--types", "steps", "--days", "2")

    assert offline == []


def test_a_rollup_that_cannot_start_fails_the_backfill_with_the_fix(
    offline, monkeypatch
):
    def unreachable(cls, url, name):
        raise TriggerError("could not reach Prefect")

    monkeypatch.setattr(cli.FlowTrigger, "by_name", classmethod(unreachable))

    with pytest.raises(HealthApiError, match="rollup rebuild --days 4"):
        run("backfill", "run", "--types", "heart-rate", "--days", "2")


def test_rebuild_covers_the_asked_days_through_tomorrow(monkeypatch):
    monkeypatch.setattr(cli, "get_session", FakeSession)
    monkeypatch.setattr(cli, "_only_user", lambda requested, session: FakeUser())
    spans = []

    class Hours:
        def __init__(self, session):
            pass

        def rebuild_in_chunks(self, health_user_id, span, on_chunk=None):
            spans.append((health_user_id, span))
            return 0

    monkeypatch.setattr(cli, "HeartRateHours", Hours)

    run("rollup", "rebuild", "--days", "30")

    [(user, span)] = spans
    today = dt.date.today()
    assert user == "fake-user"
    assert span.start == dt.datetime.combine(today - dt.timedelta(days=30), dt.time())
    assert span.end == dt.datetime.combine(today + dt.timedelta(days=2), dt.time())
