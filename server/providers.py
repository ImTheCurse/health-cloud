"""Wiring: builds the application's collaborators from configuration.

Classes elsewhere take their configuration through ``__init__`` and never read
settings themselves, which keeps them constructible in tests without an
environment. This module is the one place that bridges the two, and the caches
below are the only shared instances.
"""

import datetime as dt
from functools import lru_cache

from sqlmodel import Session

from server.auth.const import TOKEN_ISSUER
from server.auth.cookies import SessionCookies
from server.auth.google import GoogleOAuthClient
from server.auth.users import UserRepository
from server.config.const import LOCAL_ENV
from server.config.settings import get_settings
from server.crypto.sessions import SessionTokenCodec
from server.crypto.tokens import TokenCipher
from server.health.client import HealthDataClient
from server.health.credentials import AccessTokens
from server.health.fetcher import Fetcher
from server.orchestration.client import FlowTrigger
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


@lru_cache
def get_flow_trigger() -> FlowTrigger:
    """The doorbell for the fetcher deployment.

    Cached so the underlying ``requests`` session -- and its connection pool --
    is reused. Constructing it makes no call; ``trigger()`` does.
    """
    settings = get_settings()
    return FlowTrigger(
        api_url=settings.prefect_api_url,
        deployment_id=settings.prefect_deployment_id,
    )


@lru_cache
def get_health_client() -> HealthDataClient:
    """One ``requests`` session, and so one connection pool, for data reads."""
    return HealthDataClient()


def build_user_repository(session: Session) -> UserRepository:
    """Row access for ``users``, bound to one session."""
    return UserRepository(session, get_token_cipher())


def build_fetcher(session: Session) -> Fetcher:
    """The unit of work, bound to one database session.

    Not cached: a ``Session`` is not shareable between units of work, and the
    fetcher holds one. Everything expensive inside it -- the HTTP session, the
    cipher -- is cached separately.
    """
    settings = get_settings()
    repository = build_user_repository(session)
    tokens = AccessTokens(
        repository,
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
    )
    return Fetcher(get_health_client(), tokens, session)
