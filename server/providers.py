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
from server.config.const import LOCAL_ENV
from server.config.settings import get_settings
from server.crypto.sessions import SessionTokenCodec
from server.crypto.tokens import TokenCipher
from server.queue.publisher import NotificationPublisher
from server.webhooks.receiver import EndpointAuthorizer
from server.webhooks.signature import SignatureVerifier
from server.webhooks.util import authorization_value


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


@lru_cache
def get_endpoint_authorizer() -> EndpointAuthorizer:
    return EndpointAuthorizer(authorization_value(get_settings().webhook_auth_secret))


@lru_cache
def get_signature_verifier() -> SignatureVerifier:
    """Cached, so the keyset is fetched once per process rather than per call."""
    return SignatureVerifier()


@lru_cache
def get_publisher() -> NotificationPublisher:
    """The process-wide JetStream connection.

    Cached because the connection is meant to be long-lived: one warm link on
    one background event loop, opened in the app's lifespan. Constructing it
    does not connect -- ``start()`` does.

    Direct reads of the stream are enabled on a developer's machine, where
    browsing the queue is worth having, and nowhere else.
    """
    settings = get_settings()
    return NotificationPublisher(
        settings.nats_url, allow_direct=settings.environment == LOCAL_ENV
    )
