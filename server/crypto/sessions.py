"""Signing and verifying this app's own session tokens.

Google OAuth yields tokens for calling Google; none of them is a session for
this app. The access token belongs on the server only, and Google's ID token
expires in about an hour and cannot be renewed without another round trip
through Google. So once consent completes we mint our own short-lived token.
"""

import datetime as dt

import jwt

from server.crypto.const import SESSION_ALGORITHM


class SessionTokenCodec:
    """Issues and verifies HS256 tokens for cookie-borne sessions.

    ``audience`` separates token purposes: a 10-minute OAuth state token must
    never be accepted as a login, and vice versa.
    """

    def __init__(self, secret: str, issuer: str) -> None:
        if not secret:
            raise ValueError("session secret must not be empty")
        self._secret = secret
        self._issuer = issuer

    def issue(
        self,
        subject: str,
        audience: str,
        ttl: dt.timedelta,
        claims: dict[str, str] | None = None,
    ) -> str:
        now = dt.datetime.now(dt.UTC)
        return jwt.encode(
            {
                **(claims or {}),
                "iss": self._issuer,
                "sub": subject,
                "aud": audience,
                "iat": now,
                "exp": now + ttl,
            },
            self._secret,
            algorithm=SESSION_ALGORITHM,
        )

    def verify(self, token: str, audience: str) -> str | None:
        """Return the subject, or None if the token is invalid or expired."""
        claims = self.verify_claims(token, audience)
        return claims.get("sub") if claims else None

    def verify_claims(self, token: str, audience: str) -> dict | None:
        """Return every claim, or None if the token is invalid or expired.

        ``algorithms`` is pinned so a token cannot select its own algorithm.
        """
        try:
            claims = jwt.decode(
                token,
                self._secret,
                algorithms=[SESSION_ALGORITHM],
                audience=audience,
                issuer=self._issuer,
                options={"require": ["exp", "iat", "sub", "aud", "iss"]},
            )
        except jwt.InvalidTokenError:
            return None
        return claims
