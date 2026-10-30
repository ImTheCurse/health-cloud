"""Doubles for the Health API and for Google's token endpoint."""

import datetime as dt
import json
from typing import Any

import requests


class FakeResponse:
    """A response whose ``text`` really is its body.

    Both matter: ``text`` and ``json()`` are the two ways an error body can be
    picked up and put somewhere it should not be, so a fake that leaves ``text``
    empty lets a leak test pass while the leak is still possible.
    """

    def __init__(
        self, status_code: int = 200, payload: Any = None, text: str | None = None
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = (
            text
            if text is not None
            else (json.dumps(payload) if payload is not None else "")
        )

    def json(self) -> Any:
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeTransport:
    """Answers with prepared pages and records what was asked for.

    Records the query params because the *filter* is the part most easily got
    wrong: a misspelled field name is a 400, and a wrong-but-valid field silently
    narrows on the wrong thing.
    """

    def __init__(self, responses: list[FakeResponse] | None = None) -> None:
        self.responses = list(responses or [])
        self.requests: list[dict[str, Any]] = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.requests.append(
            {"url": url, "params": params or {}, "headers": headers or {}}
        )
        if not self.responses:
            return FakeResponse(200, {"dataPoints": []})
        return self.responses.pop(0)

    def post(self, url, json=None, headers=None, timeout=None):
        self.requests.append({"url": url, "json": json, "headers": headers or {}})
        if not self.responses:
            return FakeResponse(200, {"id": "run-1"})
        return self.responses.pop(0)


class ExplodingTransport:
    """A transport that cannot reach anything."""

    def __init__(self, error: Exception | None = None) -> None:
        self._error = error or requests.ConnectionError("no route to host")

    def get(self, *args, **kwargs):
        raise self._error

    def post(self, *args, **kwargs):
        raise self._error


def page(points: list[dict], next_token: str | None = None) -> FakeResponse:
    body: dict[str, Any] = {"dataPoints": points}
    if next_token is not None:
        body["nextPageToken"] = next_token
    return FakeResponse(200, body)


class FakeRepository:
    """Just enough of UserRepository for the token tests."""

    def __init__(
        self,
        refresh: str = "refresh-token",
        access: str | None = None,
        expiry: dt.datetime | None = None,
    ) -> None:
        self._refresh = refresh
        self._access = access
        self.stored: list[tuple[str, dt.datetime | None]] = []

    def refresh_token(self, user) -> str:
        return self._refresh

    def access_token(self, user) -> str | None:
        return self._access

    def store_access_token(self, user, token: str, expiry) -> None:
        self._access = token
        self.stored.append((token, expiry))
