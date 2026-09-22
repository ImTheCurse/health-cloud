"""Reading and writing the consented user."""

import datetime as dt

from sqlmodel import Session

from server.auth.const import REFRESH_TOKEN_LIFETIME
from server.crypto.tokens import TokenCipher
from server.models.user import User


class UserRepository:
    """Persistence for ``users``, scoped to one database session.

    Holds the session for its lifetime, matching how the fetcher worker and
    Dagster jobs will use it.
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


def days_until_reconsent(user: User) -> float:
    """Days left before the refresh token dies and re-consent is required."""
    expires_at = user.refreshed_at + REFRESH_TOKEN_LIFETIME
    return (expires_at - dt.datetime.now(dt.UTC)).total_seconds() / 86400
