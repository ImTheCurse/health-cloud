"""Refreshing the access token, and the one failure that is not transient.

A dead refresh token is the 7-day testing-mode expiry arriving. It has to be a
distinct exception: retrying it cannot work, it spends rate limit, and it is the
first of the three signals the expiry alert watches for.
"""

import datetime as dt

import pytest
from google.auth.exceptions import RefreshError

from server.health.credentials import AccessTokens
from server.health.error import FetchError, TokenExpiredError
from server.models.user import User
from tests.health.fakes import FakeRepository

NOW = dt.datetime.now(dt.UTC)


def a_user(expiry: dt.datetime | None = None) -> User:
    return User(
        health_user_id="1234567890123456789",
        refresh_token_enc=b"x",
        granted_scopes="",
        consented_at=NOW,
        refreshed_at=NOW,
        access_token_expiry=expiry,
    )


class FakeCredentials:
    """Stands in for google-auth's Credentials.

    ``next_error`` is a class-level knob rather than a patched method, so a test
    says what Google does without reaching into the class's bound methods.
    """

    instances: list["FakeCredentials"] = []
    next_error: Exception | None = None
    next_token: str | None = "fresh-access-token"

    def __init__(self, **kwargs):
        self.token = None
        self.expiry = NOW + dt.timedelta(hours=1)
        self.kwargs = kwargs
        FakeCredentials.instances.append(self)

    def refresh(self, request):
        if FakeCredentials.next_error is not None:
            raise FakeCredentials.next_error
        self.token = FakeCredentials.next_token


@pytest.fixture
def credentials(monkeypatch):
    FakeCredentials.instances = []
    FakeCredentials.next_error = None
    FakeCredentials.next_token = "fresh-access-token"
    monkeypatch.setattr("server.health.credentials.Credentials", FakeCredentials)
    return FakeCredentials


def tokens_for(repository, **kwargs) -> AccessTokens:
    return AccessTokens(
        repository,  # type: ignore[arg-type]
        client_id="id",
        client_secret="secret",
        refresher=lambda: object(),  # type: ignore[arg-type]
        **kwargs,
    )


def test_a_stored_token_that_is_still_good_is_reused(credentials):
    """No refresh means no call to Google, which is the common path."""
    repository = FakeRepository(access="stored-token")
    user = a_user(expiry=NOW + dt.timedelta(hours=1))

    assert tokens_for(repository).for_user(user) == "stored-token"
    assert credentials.instances == []


def test_a_token_expiring_within_the_margin_is_refreshed(credentials):
    """A token that dies mid-pagination turns one fetch into a partial one."""
    repository = FakeRepository(access="stale-token")
    user = a_user(expiry=NOW + dt.timedelta(seconds=30))

    assert tokens_for(repository).for_user(user) == "fresh-access-token"


def test_a_user_with_no_stored_token_is_refreshed(credentials):
    user = a_user(expiry=None)

    assert tokens_for(FakeRepository()).for_user(user) == "fresh-access-token"


def test_the_refreshed_token_is_stored_encrypted(credentials):
    repository = FakeRepository()

    tokens_for(repository).for_user(a_user())

    assert repository.stored == [("fresh-access-token", NOW + dt.timedelta(hours=1))]


def test_invalid_grant_is_its_own_error(credentials):
    """Not retryable: only the user re-consenting fixes it."""
    credentials.next_error = RefreshError(
        "('invalid_grant: Token has been expired or revoked.')"
    )

    with pytest.raises(TokenExpiredError, match="re-consent"):
        tokens_for(FakeRepository()).for_user(a_user())


def test_any_other_refresh_failure_stays_retryable(credentials):
    """A 503 from Google's token endpoint is worth trying again; a dead grant is
    not, and collapsing the two would either retry forever or give up too early."""
    credentials.next_error = RefreshError("Backend Error")

    with pytest.raises(FetchError):
        tokens_for(FakeRepository()).for_user(a_user())


def test_a_refresh_that_returns_no_token_is_a_failure(credentials):
    """Succeeding with nothing to show for it would hand the fetcher None."""
    credentials.next_token = None

    with pytest.raises(FetchError, match="no access token"):
        tokens_for(FakeRepository()).for_user(a_user())


def test_the_raw_user_id_never_reaches_the_log(credentials, logs):
    """A health user id plus a timestamp is a health record."""
    credentials.next_error = RefreshError("invalid_grant")
    user = a_user()

    with pytest.raises(TokenExpiredError):
        tokens_for(FakeRepository()).for_user(user)

    assert logs, "nothing was logged, so this would pass vacuously"
    assert user.health_user_id not in str([r.record["message"] for r in logs])
