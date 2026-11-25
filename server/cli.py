"""Command line entrypoints.

Run with: uv run python -m server.cli <group> <command>

Subscriber registration is deliberately a manual command rather than something
the app does at startup: it runs Google's verification handshake against the
live endpoint, and a restart quietly repointing or breaking the production
subscriber would be worse than an explicit action with visible output.

``rollup rebuild`` rewrites the hourly heart-rate summaries from the samples
already stored, in this process. It is how existing history gets summaries, and
the manual fix for hours a failed rollup run left stale.

``db reset-measurements`` drops and recreates the measurement tables, which is
how their schema changes without migrations. It cannot reach ``users``: the
refresh token lives there, and losing it means re-consenting.

Backfill is here for a different reason: nobody notified us about it. A
notification is a webhook and goes through the queue; a backfill is a decision we
made, and it calls the fetch-and-upsert unit directly. Routing it through
JetStream would put messages in the stream that Google never sent, which would
make the audit story false and confuse anyone inspecting the queue.
"""

import argparse
import datetime as dt
import sys

from sqlmodel import Session, SQLModel, select

from server.config.settings import get_settings
from server.db.session import get_session, reset_tables
from server.health.backfill import backfill_type, backfill_types
from server.health.error import HealthApiError
from server.models.datapoint import (
    ObservationSampleTime,
    ObservationTimeInterval,
    SessionSegment,
    SessionTimeInterval,
    UnknownDataPoint,
)
from server.models.notification import RawNotification
from server.models.rollup import HeartRateHour
from server.models.user import User
from server.orchestration.client import FlowTrigger
from server.orchestration.const import ROLLUP_DEPLOYMENT
from server.orchestration.error import TriggerError
from server.providers import build_fetcher, build_user_repository
from server.rollup.const import MAX_UTC_OFFSET, ROLLED_UP_TYPES
from server.rollup.hours import HeartRateHours, HourSpan
from server.webhooks.const import (
    DATA_TYPES,
    WEBHOOK_PATH,
    SubscriptionPolicy,
)
from server.webhooks.error import SubscriberError
from server.webhooks.subscriber import SubscriberClient, describe

#: Google retries undelivered notifications for 7 days and a testing-mode refresh
#: token lives 7 days, so a 7-day backfill covers anything the webhook missed.
#: ``--days`` reaches further: ``list`` serves months of history.
BACKFILL_DAYS = 7


def build_client() -> SubscriberClient:
    settings = get_settings()
    return SubscriberClient.from_service_account_file(
        settings.gcp_project_number, settings.google_application_credentials
    )


def build_endpoint(override: str | None) -> str:
    settings = get_settings()
    origin = (override or settings.webhook_public_url).rstrip("/")
    if not origin:
        raise SubscriberError(
            "no endpoint given and WEBHOOK_PUBLIC_URL is empty. Start a tunnel "
            "and pass --endpoint https://<host>, or set it in .env."
        )
    return f"{origin}{WEBHOOK_PATH}"


def subscriber_list(args: argparse.Namespace) -> None:
    subscribers = build_client().list()
    if not subscribers:
        print("no subscribers registered on this project")
        return
    for subscriber in subscribers:
        print(describe(subscriber))


def subscriber_create(args: argparse.Namespace) -> None:
    settings = get_settings()
    endpoint = build_endpoint(args.endpoint)
    # Check before announcing, so a rejected URL does not print an optimistic
    # "Google is verifying ..." that never happened.
    SubscriberClient.validate(settings.subscriber_id, endpoint)

    print(f"registering {settings.subscriber_id} -> {endpoint}")
    print("Google is now calling that endpoint to verify it ...")

    subscriber = build_client().create(
        subscriber_id=settings.subscriber_id,
        endpoint_uri=endpoint,
        secret=settings.webhook_auth_secret,
        policy=args.policy,
    )
    print(describe(subscriber))


def subscriber_patch(args: argparse.Namespace) -> None:
    settings = get_settings()
    endpoint = build_endpoint(args.endpoint)
    SubscriberClient.validate(settings.subscriber_id, endpoint)

    print(f"repointing {settings.subscriber_id} -> {endpoint}")
    subscriber = build_client().patch(settings.subscriber_id, endpoint)
    print(describe(subscriber))


def subscriber_sync_types(args: argparse.Namespace) -> None:
    settings = get_settings()
    print(f"subscribing {settings.subscriber_id} to {len(DATA_TYPES)} data types")
    subscriber = build_client().sync_types(settings.subscriber_id, policy=args.policy)
    print(describe(subscriber))


def subscriber_delete(args: argparse.Namespace) -> None:
    settings = get_settings()
    build_client().delete(settings.subscriber_id, force=args.force)
    print(f"deleted {settings.subscriber_id}")


def db_reset_measurements(args: argparse.Namespace) -> None:
    """Drop the measurement tables and recreate them empty.

    The list is fixed here rather than taken as an argument, so ``users`` cannot
    be named by mistake. Without ``--force`` it only says what it would drop.
    """
    models: list[type[SQLModel]] = [
        ObservationTimeInterval,
        ObservationSampleTime,
        SessionTimeInterval,
        SessionSegment,
        UnknownDataPoint,
        HeartRateHour,
    ]
    if args.include_audit:
        models.append(RawNotification)
    names = ", ".join(model.__table__.name for model in models)  # type: ignore[attr-defined]

    if not args.force:
        print(f"would drop and recreate, empty: {names}")
        print("nothing changed; rerun with --force")
        raise SystemExit(1)

    reset_tables(models)
    print(f"dropped and recreated, empty: {names}")
    print("refill with: backfill run --days N")


def backfill_run(args: argparse.Namespace) -> None:
    """Fetch a window nobody notified us about.

    The strategy per type is in ``server.health.backfill``, shared with the
    scheduled ``backfill-recent`` flow.

    Sequential by design. The limit is 300 requests a minute for one user, and a
    backfill over several types is the one thing here capable of reaching it.
    """
    end = dt.datetime.now(dt.UTC) if args.until is None else _day(args.until)
    start = end - dt.timedelta(days=args.days)
    types = args.types or backfill_types()

    with get_session() as session:
        user = _only_user(args.user, session)
        fetcher = build_fetcher(session)
        print(f"backfilling {args.days} day(s) up to {end.date()} for {len(types)} type(s)")
        for data_type in types:
            backfill_type(fetcher, user, data_type, start, end, progress=_print)
        health_user_id = user.health_user_id

    if ROLLED_UP_TYPES & set(types):
        _request_rollup(health_user_id, start, end)


def _request_rollup(health_user_id: str, start: dt.datetime, end: dt.datetime) -> None:
    """Start a rollup run over every local hour the backfilled window can touch.

    The window is in UTC and the hours are local, so it is widened by the
    largest UTC offset either way. Hours with nothing in them are rebuilt as
    empty, which costs a query and changes nothing.
    """
    span = HourSpan.around(
        (start - MAX_UTC_OFFSET).replace(tzinfo=None),
        (end + MAX_UTC_OFFSET).replace(tzinfo=None),
    )
    try:
        trigger = FlowTrigger.by_name(get_settings().prefect_api_url, ROLLUP_DEPLOYMENT)
        run_id = trigger.trigger(
            {
                "health_user_id": health_user_id,
                "start": span.start.isoformat(),
                "end": span.end.isoformat(),
            }
        )
    except TriggerError as error:
        days = (end - start).days + 2
        raise HealthApiError(
            f"the heart-rate rollup was not started ({error}); "
            f"rebuild by hand with: rollup rebuild --days {days}"
        ) from error
    print(f"requested a heart-rate rollup run {run_id or ''}".rstrip(), flush=True)


def rollup_rebuild(args: argparse.Namespace) -> None:
    """Rebuild the hourly heart-rate summaries from the stored samples.

    Covers the last ``--days`` local days up to the end of tomorrow, so the
    current hour is included wherever the user's clock is. Committed a day at a
    time, so an interrupted rebuild keeps the days it finished.
    """
    today = dt.date.today()
    start = dt.datetime.combine(today - dt.timedelta(days=args.days), dt.time())
    end = dt.datetime.combine(today + dt.timedelta(days=2), dt.time())

    def report(chunk: HourSpan, written: int) -> None:
        print(f"  {chunk.start.date()}: {written} hour(s)", flush=True)

    with get_session() as session:
        user = _only_user(args.user, session)
        print(f"rebuilding heart-rate hours from {start.date()} to {end.date()}")
        written = HeartRateHours(session).rebuild_in_chunks(
            user.health_user_id, HourSpan(start, end), on_chunk=report
        )
    print(f"rebuilt {written} hour(s)")


def _print(line: str) -> None:
    print(line, flush=True)


def _only_user(requested: str | None, session: Session) -> User:
    """The user to backfill.

    Single-user by design, so the id is optional: if exactly one person has
    consented, that is who is meant. Asking for an id that is not there fails
    rather than silently doing nothing.
    """
    repository = build_user_repository(session)
    if requested is not None:
        user = repository.get(requested)
        if user is None:
            raise HealthApiError(f"no consented user with id {requested}")
        return user

    users = list(session.exec(select(User)))
    if len(users) != 1:
        raise HealthApiError(
            f"{len(users)} consented users found; name one with --user"
        )
    return users[0]


def _day(value: str) -> dt.datetime:
    """A ``YYYY-MM-DD`` boundary, at midnight UTC."""
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError as error:
        raise HealthApiError(f"--until must be YYYY-MM-DD, not {value!r}") from error
    return dt.datetime.combine(parsed, dt.time(), tzinfo=dt.UTC)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="server.cli")
    groups = parser.add_subparsers(dest="group", required=True)

    subscriber = groups.add_parser("subscriber", help="manage the webhook subscriber")
    commands = subscriber.add_subparsers(dest="command", required=True)

    listing = commands.add_parser("list", help="show this project's subscribers")
    listing.set_defaults(handler=subscriber_list)

    creating = commands.add_parser("create", help="register the webhook endpoint")
    creating.add_argument(
        "--endpoint",
        help="public https origin, overriding WEBHOOK_PUBLIC_URL",
    )
    creating.add_argument(
        "--policy",
        type=SubscriptionPolicy,
        choices=list(SubscriptionPolicy),
        default=SubscriptionPolicy.AUTOMATIC,
    )
    creating.set_defaults(handler=subscriber_create)

    patching = commands.add_parser("patch", help="repoint at a different endpoint")
    patching.add_argument("--endpoint", help="new public https origin")
    patching.set_defaults(handler=subscriber_patch)

    syncing = commands.add_parser(
        "sync-types", help="subscribe to every data type in DATA_TYPES"
    )
    syncing.add_argument(
        "--policy",
        type=SubscriptionPolicy,
        choices=list(SubscriptionPolicy),
        default=SubscriptionPolicy.AUTOMATIC,
    )
    syncing.set_defaults(handler=subscriber_sync_types)

    deleting = commands.add_parser("delete", help="remove the registration")
    deleting.add_argument("--force", action="store_true")
    deleting.set_defaults(handler=subscriber_delete)

    db = groups.add_parser("db", help="manage the app database's tables")
    db_commands = db.add_subparsers(dest="command", required=True)
    resetting = db_commands.add_parser(
        "reset-measurements",
        help="drop the measurement tables and recreate them empty; users is kept",
    )
    resetting.add_argument("--force", action="store_true", help="actually drop them")
    resetting.add_argument(
        "--include-audit",
        action="store_true",
        help="also drop raw_notifications, the webhook audit log",
    )
    resetting.set_defaults(handler=db_reset_measurements)

    backfill = groups.add_parser(
        "backfill", help="fetch a past window directly, bypassing the queue"
    )
    backfill_commands = backfill.add_subparsers(dest="command", required=True)
    running = backfill_commands.add_parser("run", help="fetch and upsert a window")
    running.add_argument(
        "--types",
        nargs="+",
        help="data types to fetch, e.g. --types steps sleep heart-rate "
        "(default: every subscribed type that can be fetched)",
    )
    running.add_argument(
        "--days",
        type=int,
        default=BACKFILL_DAYS,
        help=f"how far back to reach (default {BACKFILL_DAYS}, the retry window)",
    )
    running.add_argument(
        "--until",
        help="end of the window as YYYY-MM-DD (default: now)",
    )
    running.add_argument("--user", help="health user id (default: the only one)")
    running.set_defaults(handler=backfill_run)

    rollup = groups.add_parser("rollup", help="manage the stored summaries")
    rollup_commands = rollup.add_subparsers(dest="command", required=True)
    rebuilding = rollup_commands.add_parser(
        "rebuild", help="rebuild the hourly heart-rate summaries from stored samples"
    )
    rebuilding.add_argument(
        "--days",
        type=int,
        default=BACKFILL_DAYS,
        help=f"how many past days to rebuild (default {BACKFILL_DAYS})",
    )
    rebuilding.add_argument("--user", help="health user id (default: the only one)")
    rebuilding.set_defaults(handler=rollup_rebuild)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        args.handler(args)
    except (SubscriberError, HealthApiError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
