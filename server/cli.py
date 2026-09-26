"""Command line entrypoints.

Run with: uv run python -m server.cli <group> <command>

Subscriber registration is deliberately a manual command rather than something
the app does at startup: it runs Google's verification handshake against the
live endpoint, and a restart quietly repointing or breaking the production
subscriber would be worse than an explicit action with visible output.
"""

import argparse
import sys

from server.config.settings import get_settings
from server.webhooks.const import WEBHOOK_PATH, SubscriptionPolicy
from server.webhooks.error import SubscriberError
from server.webhooks.subscriber import SubscriberClient, describe


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


def subscriber_delete(args: argparse.Namespace) -> None:
    settings = get_settings()
    build_client().delete(settings.subscriber_id, force=args.force)
    print(f"deleted {settings.subscriber_id}")


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

    deleting = commands.add_parser("delete", help="remove the registration")
    deleting.add_argument("--force", action="store_true")
    deleting.set_defaults(handler=subscriber_delete)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        args.handler(args)
    except SubscriberError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
