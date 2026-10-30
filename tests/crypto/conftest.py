"""Fixtures for the crypto tests, all built from throwaway keys.

Nothing here touches the environment: a test that fails must mean the code is
wrong, not that .env is.
"""

import secrets

import pytest

from server.auth.const import TOKEN_ISSUER
from server.crypto.sessions import SessionTokenCodec


@pytest.fixture
def codec() -> SessionTokenCodec:
    return SessionTokenCodec(secrets.token_hex(32), TOKEN_ISSUER)
