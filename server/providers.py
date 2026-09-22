"""Wiring: builds the application's collaborators from configuration.

Classes elsewhere take their configuration through ``__init__`` and never read
settings themselves, which keeps them constructible in tests without an
environment. This module is the one place that bridges the two, and the caches
below are the only shared instances.
"""

import datetime as dt
from functools import lru_cache

from server.auth.const import TOKEN_ISSUER
from server.auth.cookies import SessionCookies
from server.auth.google import GoogleOAuthClient
from server.config.settings import get_settings
from server.crypto.sessions import SessionTokenCodec
from server.crypto.tokens import TokenCipher


@lru_cache
def get_token_cipher() -> TokenCipher:
    return TokenCipher.from_hex(get_settings().token_encryption_key)


@lru_cache
def get_session_codec() -> SessionTokenCodec:
    return SessionTokenCodec(get_settings().session_secret, TOKEN_ISSUER)


@lru_cache
def get_oauth_client() -> GoogleOAuthClient:
    settings = get_settings()
    return GoogleOAuthClient(
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        redirect_uri=settings.google_redirect_uri,
    )


@lru_cache
def get_session_cookies() -> SessionCookies:
    settings = get_settings()
    return SessionCookies(
        secure=settings.cookie_secure,
        session_ttl=dt.timedelta(minutes=settings.session_ttl_minutes),
    )
