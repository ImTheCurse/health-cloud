"""Verify the subscriber service account key and its IAM role.

Run: uv run python scripts/check_service_account.py

Two separate things can be wrong, and they need different fixes, so this
reports them separately:

- the key itself is missing, malformed, or for the wrong kind of account
- the key is fine but the service account lacks the Health role
"""

import json
import os
import pathlib
import sys

ENV_FILE = pathlib.Path(".env")
SCOPE = "https://www.googleapis.com/auth/cloud-platform"


def fail(message: str) -> None:
    print(f"  FAILED: {message}", file=sys.stderr)
    sys.exit(1)


def setting(name: str, default: str | None = None) -> str | None:
    """Read a value from the environment, then from .env."""
    if value := os.environ.get(name):
        return value
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            key, separator, value = line.partition("=")
            if separator and key.strip() == name and value.strip():
                return value.strip()
    return default


def main() -> None:
    project_number = setting("GCP_PROJECT_NUMBER")
    if not project_number:
        fail(
            "GCP_PROJECT_NUMBER is not set, in the environment or in .env. "
            "Run scripts/setup-service-account.sh, or export it."
        )

    key_file = pathlib.Path(
        setting("GOOGLE_APPLICATION_CREDENTIALS", "service-account.json")
    )
    if not key_file.exists():
        fail(f"{key_file} not found. Move the downloaded key here.")

    try:
        key = json.loads(key_file.read_text())
    except json.JSONDecodeError as exc:
        fail(f"{key_file} is not valid JSON: {exc}")

    if key.get("type") != "service_account":
        fail(
            f"{key_file} has type={key.get('type')!r}. That is an OAuth client, "
            "not a service account key."
        )
    print(f"  key belongs to {key.get('client_email')}")

    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account

    credentials = service_account.Credentials.from_service_account_file(
        str(key_file), scopes=[SCOPE]
    )
    session = AuthorizedSession(credentials)

    url = f"https://health.googleapis.com/v4/projects/{project_number}/subscribers"
    response = session.get(url, timeout=30)

    if response.status_code == 403:
        fail(
            "the key works, but this account lacks permission to manage "
            "subscribers. Grant it 'Google Health API Admin' in IAM.\n"
            f"  Google said: {response.text[:300]}"
        )
    if response.status_code == 404:
        fail(
            "project not found, or the Google Health API is not enabled on it.\n"
            f"  Google said: {response.text[:300]}"
        )
    if not response.ok:
        fail(f"HTTP {response.status_code}: {response.text[:300]}")

    subscribers = response.json().get("subscribers", [])
    print(f"  role confirmed: listed {len(subscribers)} subscriber(s)")
    for subscriber in subscribers:
        print(f"    - {subscriber.get('name')} -> {subscriber.get('endpointUri')}")


if __name__ == "__main__":
    main()
