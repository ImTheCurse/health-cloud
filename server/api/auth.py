"""Authentication routes.

One flow does both jobs: signing in to this app and granting Google Health
consent. Re-consent is the same flow again, which is why it can be a single
button.
"""

import datetime as dt

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from server.auth.const import (
    CODE_VERIFIER_CLAIM,
    SESSION_AUDIENCE,
    STATE_AUDIENCE,
    STATE_TTL,
)
from server.auth.cookies import SessionCookies
from server.auth.google import GoogleOAuthClient
from server.auth.users import UserRepository, days_until_reconsent
from server.config.settings import Settings, get_settings
from server.crypto.sessions import SessionTokenCodec
from server.db.session import SessionDep
from server.models.user import User
from server.providers import (
    get_oauth_client,
    get_session_codec,
    get_session_cookies,
    get_token_cipher,
)

router = APIRouter(prefix="/auth", tags=["auth"])

OAuthClient = Depends(get_oauth_client)
Codec = Depends(get_session_codec)
Cookies = Depends(get_session_cookies)
Config = Depends(get_settings)


def get_user_repository(session: SessionDep) -> UserRepository:
    return UserRepository(session, get_token_cipher())


Users = Depends(get_user_repository)


def current_user(
    users: UserRepository = Users,
    codec: SessionTokenCodec = Codec,
    health_cloud_session: str | None = Cookie(default=None),
) -> User:
    """Resolve the session cookie to a user, or 401."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated"
    )
    if not health_cloud_session:
        raise unauthorized

    health_user_id = codec.verify(health_cloud_session, SESSION_AUDIENCE)
    if health_user_id is None:
        raise unauthorized

    user = users.get(health_user_id)
    if user is None:
        raise unauthorized
    return user


CurrentUser = Depends(current_user)


@router.get("/google/login")
def google_login(
    oauth: GoogleOAuthClient = OAuthClient,
    codec: SessionTokenCodec = Codec,
    cookies: SessionCookies = Cookies,
) -> RedirectResponse:
    """Start consent. Also the one-click re-consent entry point."""
    url, state, code_verifier = oauth.authorization_url()
    response = RedirectResponse(url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    # The PKCE verifier rides along in the signed, httpOnly state cookie: it
    # must reach the callback, and it must never reach Google until the
    # exchange.
    cookies.set_state(
        response,
        codec.issue(
            state, STATE_AUDIENCE, STATE_TTL, claims={CODE_VERIFIER_CLAIM: code_verifier}
        ),
    )
    return response


@router.get("/google/callback")
def google_callback(
    request: Request,
    oauth: GoogleOAuthClient = OAuthClient,
    codec: SessionTokenCodec = Codec,
    cookies: SessionCookies = Cookies,
    users: UserRepository = Users,
    settings: Settings = Config,
    health_cloud_oauth_state: str | None = Cookie(default=None),
) -> RedirectResponse:
    error = request.query_params.get("error")
    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    code = request.query_params.get("code")
    returned_state = request.query_params.get("state")
    if not code or not returned_state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="missing code or state"
        )

    # The state cookie is this callback's CSRF defence: it proves the redirect
    # was started by this browser, in this session, within the last 10 minutes.
    state_claims = (
        codec.verify_claims(health_cloud_oauth_state, STATE_AUDIENCE)
        if health_cloud_oauth_state
        else None
    )
    if state_claims is None or state_claims.get("sub") != returned_state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid oauth state"
        )

    code_verifier = state_claims.get(CODE_VERIFIER_CLAIM)
    if not code_verifier:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="missing code verifier"
        )

    credentials = oauth.exchange_code(code, returned_state, code_verifier)
    health_user_id = oauth.fetch_health_user_id(credentials.token)
    google_sub, email, display_name = oauth.identity_claims(credentials)

    users.upsert(
        health_user_id=health_user_id,
        credentials=credentials,
        google_sub=google_sub,
        email=email,
        display_name=display_name,
    )

    response = RedirectResponse(
        settings.frontend_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT
    )
    session_ttl = dt.timedelta(minutes=settings.session_ttl_minutes)
    cookies.set_session(
        response, codec.issue(health_user_id, SESSION_AUDIENCE, session_ttl)
    )
    cookies.clear_state(response)
    return response


@router.post("/logout")
def logout(response: Response, cookies: SessionCookies = Cookies) -> dict[str, str]:
    cookies.clear_session(response)
    return {"status": "logged out"}


@router.get("/me")
def me(user: User = CurrentUser) -> dict:
    return {
        "health_user_id": user.health_user_id,
        "email": user.email,
        "display_name": user.display_name,
        "granted_scopes": user.granted_scopes.split(),
        "consented_at": user.consented_at,
    }


@router.get("/status")
def connection_status(user: User = CurrentUser) -> dict:
    """Connection health, for the re-consent banner."""
    remaining = days_until_reconsent(user)
    return {
        "connected": user.revoked_at is None and remaining > 0,
        "days_until_reconsent": round(remaining, 2),
        "needs_reconsent": remaining <= 0 or user.revoked_at is not None,
        "refreshed_at": user.refreshed_at,
    }
