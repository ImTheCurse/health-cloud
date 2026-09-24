"""Issuing and verifying the signed tokens the cookies carry."""

import datetime as dt

import pytest

from server.auth.const import SESSION_AUDIENCE, TOKEN_ISSUER
from server.crypto.sessions import SessionTokenCodec

TTL = dt.timedelta(minutes=60)


def test_token_round_trips(codec):
    token = codec.issue("health-user-1", SESSION_AUDIENCE, TTL)

    assert codec.verify(token, SESSION_AUDIENCE) == "health-user-1"


def test_expired_token_is_rejected(codec):
    expired = codec.issue("health-user-1", SESSION_AUDIENCE, dt.timedelta(seconds=-1))

    assert codec.verify(expired, SESSION_AUDIENCE) is None


def test_empty_secret_is_refused():
    with pytest.raises(ValueError, match="secret"):
        SessionTokenCodec("", TOKEN_ISSUER)
