"""Audience separation between the two tokens this codec issues.

One codec and one secret sign both the 10-minute OAuth state token and the
session cookie. The audience claim is the only thing keeping them apart.
"""

import datetime as dt

from server.auth.const import SESSION_AUDIENCE, STATE_AUDIENCE

TTL = dt.timedelta(minutes=60)


def test_a_state_token_cannot_log_anyone_in(codec):
    state = codec.issue("some-state", STATE_AUDIENCE, TTL)

    assert codec.verify(state, SESSION_AUDIENCE) is None


def test_a_session_token_is_not_accepted_as_state(codec):
    token = codec.issue("health-user-1", SESSION_AUDIENCE, TTL)

    assert codec.verify(token, STATE_AUDIENCE) is None
