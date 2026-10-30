"""Tokens an attacker might present to the session cookie."""

import datetime as dt
import secrets

import jwt

from server.auth.const import SESSION_AUDIENCE, TOKEN_ISSUER
from server.crypto.sessions import SessionTokenCodec

TTL = dt.timedelta(minutes=60)


def test_tampered_token_is_rejected(codec):
    token = codec.issue("health-user-1", SESSION_AUDIENCE, TTL)
    tampered = token[:-2] + ("aa" if not token.endswith("aa") else "bb")

    assert codec.verify(tampered, SESSION_AUDIENCE) is None


def test_a_token_from_another_secret_is_rejected(codec):
    other = SessionTokenCodec(secrets.token_hex(32), TOKEN_ISSUER)
    token = other.issue("health-user-1", SESSION_AUDIENCE, TTL)

    assert codec.verify(token, SESSION_AUDIENCE) is None


def test_an_unsigned_token_is_rejected(codec):
    """alg=none must not be accepted; algorithms are pinned on decode."""
    now = dt.datetime.now(dt.UTC)
    forged = jwt.encode(
        {
            "iss": TOKEN_ISSUER,
            "sub": "attacker",
            "aud": SESSION_AUDIENCE,
            "iat": now,
            "exp": now + TTL,
        },
        key="",
        algorithm="none",
    )

    assert codec.verify(forged, SESSION_AUDIENCE) is None
