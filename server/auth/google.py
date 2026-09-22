"""The Google OAuth flow and Health API identity lookup."""

import os

import requests
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow

from server.auth.const import (
    AUTH_URI,
    HTTP_TIMEOUT_SECONDS,
    IDENTITY_URI,
    SCOPES,
    TOKEN_URI,
)

# Google returns granted scopes in its own order and may normalise entries
# (notably `openid`). Without this, oauthlib raises on the difference.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")


class GoogleOAuthClient:
    """Drives the three-legged flow against one OAuth client."""

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri

    def _build_flow(
        self, state: str | None = None, code_verifier: str | None = None
    ) -> Flow:
        client_config = {
            "web": {
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "auth_uri": AUTH_URI,
                "token_uri": TOKEN_URI,
                "redirect_uris": [self._redirect_uri],
            }
        }
        flow = Flow.from_client_config(
            client_config,
            scopes=SCOPES,
            state=state,
            code_verifier=code_verifier,
            autogenerate_code_verifier=code_verifier is None,
        )
        flow.redirect_uri = self._redirect_uri
        return flow

    def authorization_url(self) -> tuple[str, str, str]:
        """Return ``(url, state, code_verifier)`` for the consent redirect.

        PKCE is on by default in this library: the Flow generates a verifier
        here and sends only its challenge to Google. The verifier must survive
        until the callback, because a fresh Flow built on that later request
        would not have it and Google rejects the exchange with
        "Missing code verifier".

        ``access_type=offline`` with ``prompt=consent`` is what makes Google
        return a refresh token. Without ``prompt=consent`` Google omits it on
        repeat authorisations, which would break re-consent -- the one flow
        this project must perform reliably every 7 days.
        """
        flow = self._build_flow()
        url, state = flow.authorization_url(
            access_type="offline",
            prompt="consent",
            include_granted_scopes="true",
        )
        return url, state, flow.code_verifier

    def exchange_code(self, code: str, state: str, code_verifier: str):
        """Swap the callback's authorization code for credentials.

        ``code_verifier`` is the PKCE secret issued alongside the redirect; the
        exchange fails without it.
        """
        flow = self._build_flow(state=state, code_verifier=code_verifier)
        flow.fetch_token(code=code)
        return flow.credentials

    def fetch_health_user_id(self, access_token: str) -> str:
        """Look up the caller's healthUserId.

        The token response never contains it, so this call is part of
        onboarding.
        """
        response = requests.get(
            IDENTITY_URI,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()["healthUserId"]

    def identity_claims(self, credentials) -> tuple[str | None, str | None, str | None]:
        """Read ``(sub, email, name)`` from the ID token, if one was returned.

        Verified against Google's public keys, which also confirms the audience
        is our own client id. Returns all-None when no ID token came back, so
        the health scopes still work on their own.
        """
        raw = getattr(credentials, "id_token", None)
        if not raw:
            return None, None, None

        claims = id_token.verify_oauth2_token(
            raw, google_requests.Request(), self._client_id
        )
        return claims.get("sub"), claims.get("email"), claims.get("name")
