"""Reading and writing the consented user."""

import datetime as dt

from sqlmodel import Session

from server.crypto.tokens import TokenCipher
from server.models.user import User


def _aware(moment: dt.datetime | None) -> dt.datetime | None:
    """google-auth returns a naive UTC expiry; the column is timezone-aware."""
    if moment is None:
        return None
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=dt.UTC)


class UserRepository:
    """Persistence for ``users``, scoped to one database session.

    Holds the session for its lifetime, matching how the fetcher flow uses it.
    """

    def __init__(self, session: Session, cipher: TokenCipher) -> None:
        self._session = session
        self._cipher = cipher

    def get(self, health_user_id: str) -> User | None:
        return self._session.get(User, health_user_id)

    def upsert(
        self,
        *,
        health_user_id: str,
        credentials,
        google_sub: str | None,
        email: str | None,
        display_name: str | None,
    ) -> User:
        now = dt.datetime.now(dt.UTC)
        user = self.get(health_user_id)

        if user is None:
            user = User(
                health_user_id=health_user_id,
                refresh_token_enc=b"",
                granted_scopes="",
                consented_at=now,
                refreshed_at=now,
            )

        # Google omits the refresh token on some re-authorisations; keep the
        # stored one rather than overwriting it with nothing.
        if credentials.refresh_token:
            user.refresh_token_enc = self._cipher.encrypt(
                credentials.refresh_token, health_user_id
            )
        if credentials.token:
            user.access_token_enc = self._cipher.encrypt(
                credentials.token, health_user_id
            )

        user.access_token_expiry = credentials.expiry
        user.granted_scopes = " ".join(credentials.scopes or [])
        user.google_sub = google_sub
        user.email = email
        user.display_name = display_name
        user.refreshed_at = now
        user.revoked_at = None

        self._session.add(user)
        self._session.commit()
        self._session.refresh(user)
        return user

    def refresh_token(self, user: User) -> str:
        return self._cipher.decrypt(user.refresh_token_enc, user.health_user_id)

    def access_token(self, user: User) -> str | None:
        """The stored access token, or None if there is not one yet.

        Encrypted at rest like the refresh token. It is short-lived, but for that
        hour it reads the same health data.
        """
        if user.access_token_enc is None:
            return None
        return self._cipher.decrypt(user.access_token_enc, user.health_user_id)

    def store_access_token(
        self, user: User, token: str, expiry: dt.datetime | None
    ) -> None:
        """Record a freshly refreshed access token.

        ``refreshed_at`` is deliberately *not* touched: it records when consent
        was last granted, and the 7-day expiry countdown and its push alert are
        computed from it. Moving it on every hourly refresh would reset that
        countdown and hide the expiry until the moment it broke.
        """
        user.access_token_enc = self._cipher.encrypt(token, user.health_user_id)
        user.access_token_expiry = _aware(expiry)
        self._session.add(user)
        self._session.commit()
        self._session.refresh(user)
