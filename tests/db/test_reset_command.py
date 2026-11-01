"""``db reset-measurements``: what it drops, and what it never drops.

Needs no database: the drop itself is replaced, so these check which tables the
command would hand to it.
"""

import pytest

from server import cli


@pytest.fixture
def dropped(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(
        cli,
        "reset_tables",
        lambda models: calls.append([model.__table__.name for model in models]),
    )
    return calls


def run(*argv: str) -> None:
    args = cli.build_parser().parse_args(["db", "reset-measurements", *argv])
    args.handler(args)


def test_without_force_nothing_is_dropped(dropped, capsys):
    with pytest.raises(SystemExit):
        run()

    assert dropped == []
    assert "rerun with --force" in capsys.readouterr().out


def test_force_drops_every_measurement_table(dropped):
    run("--force")

    assert sorted(dropped[0]) == [
        "observation_sample_times",
        "observation_time_intervals",
        "session_segments",
        "session_time_intervals",
        "unknown_data_points",
    ]


def test_the_audit_log_is_kept_unless_asked_for(dropped):
    run("--force")
    run("--force", "--include-audit")

    assert "raw_notifications" not in dropped[0]
    assert "raw_notifications" in dropped[1]


def test_users_is_never_dropped(dropped):
    """The refresh token lives there; dropping it means re-consenting."""
    run("--force", "--include-audit")

    assert "users" not in dropped[0]
