"""Keeping a usable access token in front of the fetcher.

Its own module rather than a method on ``UserRepository``, which touches no
network today: refreshing is an HTTP call whose interesting outcome is a policy
decision -- the refresh token is dead and only the user can fix it -- and that
belongs next to the code that fetches, not next to the code that stores rows.
"""

import datetime as dt

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from loguru import logger

from server.auth.users import UserRepository
from server.health.const import EXPIRY_MARGIN_SECONDS, TOKEN_URI
from server.health.error import FetchError, TokenExpiredError
from server.models.user import User
from server.observability.util import hashed_log_id


class AccessTokens:
    """Hands out a live access token for a user, refreshing when needed.

    Configuration arrives through ``__init__`` and never by reading settings, so
    it is constructible in a test without an environment.
    """

    def __init__(
        self,
        repository: UserRepository,
        client_id: str,
        client_secret: str,
        token_uri: str = TOKEN_URI,
        margin_seconds: int = EXPIRY_MARGIN_SECONDS,
        refresher: type[Request] = Request,
    ) -> None:
        self._repository = repository
        self._client_id = client_id
        self._client_secret = client_secret
        self._token_uri = token_uri
        self._margin = dt.timedelta(seconds=margin_seconds)
        self._refresher = refresher

    def for_user(self, user: User) -> str:
        """A token good for the next few minutes at least.

        The margin matters: a token that expires mid-pagination turns one fetch
        into a partial one, and the 401 would arrive on page three.

        Raises:
            TokenExpiredError: the refresh token is dead; only re-consent fixes
                it. Deliberately distinct, so a caller does not retry it into a
                rate limit and so the token-expiry alert can key off it.
            FetchError: the refresh failed for some other reason, and is worth
                retrying.
        """
        if self._still_valid(user):
            stored = self._repository.access_token(user)
            if stored is not None:
                return stored

        return self._refresh(user)

    def _still_valid(self, user: User) -> bool:
        expiry = user.access_token_expiry
        if expiry is None:
            return False
        if expiry.tzinfo is None:  # written before the column was tz-aware
            expiry = expiry.replace(tzinfo=dt.UTC)
        return expiry - self._margin > dt.datetime.now(dt.UTC)

    def _refresh(self, user: User) -> str:
        credentials = Credentials(
            token=None,
            refresh_token=self._repository.refresh_token(user),
            token_uri=self._token_uri,
            client_id=self._client_id,
            client_secret=self._client_secret,
        )
        try:
            credentials.refresh(self._refresher())
        except RefreshError as error:
            # `invalid_grant` is the 7-day testing-mode expiry arriving. It is not
            # transient and no number of retries will help.
            if _is_invalid_grant(error):
                logger.warning(
                    "refresh token rejected for user {}; re-consent required",
                    hashed_log_id(user.health_user_id),
                )
                raise TokenExpiredError(
                    "refresh token was rejected; the user must re-consent"
                ) from error
            raise FetchError(f"token refresh failed: {type(error).__name__}") from error

        if not credentials.token:
            raise FetchError("token refresh returned no access token")

        self._repository.store_access_token(user, credentials.token, credentials.expiry)
        return credentials.token


def _is_invalid_grant(error: RefreshError) -> bool:
    """Whether Google said the grant itself is bad.

    Matched on the error text because ``google-auth`` does not expose the OAuth
    error code as a field. Kept in one place so the fragility is visible rather
    than repeated.
    """
    return "invalid_grant" in str(error).lower()
