import datetime as dt
import secrets

import pytest

from server.auth.const import SESSION_AUDIENCE, STATE_AUDIENCE, TOKEN_ISSUER
from server.crypto.sessions import SessionTokenCodec

TTL = dt.timedelta(minutes=60)


@pytest.fixture
def codec() -> SessionTokenCodec:
    return SessionTokenCodec(secrets.token_hex(32), TOKEN_ISSUER)


def test_token_round_trips(codec):
    token = codec.issue("health-user-1", SESSION_AUDIENCE, TTL)

    assert codec.verify(token, SESSION_AUDIENCE) == "health-user-1"


def test_tampered_token_is_rejected(codec):
    token = codec.issue("health-user-1", SESSION_AUDIENCE, TTL)
    tampered = token[:-2] + ("aa" if not token.endswith("aa") else "bb")

    assert codec.verify(tampered, SESSION_AUDIENCE) is None


def test_a_state_token_cannot_log_anyone_in(codec):
    """Audience separation: the 10-minute OAuth state token is not a session."""
    state = codec.issue("some-state", STATE_AUDIENCE, TTL)

    assert codec.verify(state, SESSION_AUDIENCE) is None


def test_a_session_token_is_not_accepted_as_state(codec):
    token = codec.issue("health-user-1", SESSION_AUDIENCE, TTL)

    assert codec.verify(token, STATE_AUDIENCE) is None


def test_expired_token_is_rejected(codec):
    expired = codec.issue("health-user-1", SESSION_AUDIENCE, dt.timedelta(seconds=-1))

    assert codec.verify(expired, SESSION_AUDIENCE) is None


def test_a_token_from_another_secret_is_rejected(codec):
    other = SessionTokenCodec(secrets.token_hex(32), TOKEN_ISSUER)
    token = other.issue("health-user-1", SESSION_AUDIENCE, TTL)

    assert codec.verify(token, SESSION_AUDIENCE) is None


def test_an_unsigned_token_is_rejected(codec):
    """alg=none must not be accepted; algorithms are pinned on decode."""
    import jwt

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


def test_empty_secret_is_refused():
    with pytest.raises(ValueError, match="secret"):
        SessionTokenCodec("", TOKEN_ISSUER)
