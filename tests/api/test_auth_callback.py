"""The callback's own defences, before any token exchange is attempted.

Every case here is rejected without reaching Google, so none of them needs the
network.
"""

from server.auth.const import OAUTH_STATE_COOKIE, STATE_AUDIENCE, STATE_TTL
from server.providers import get_session_codec


def test_callback_rejects_a_missing_state(client):
    response = client.get("/auth/google/callback?code=abc", follow_redirects=False)

    assert response.status_code == 400


def test_callback_rejects_a_forged_state(client):
    """A state the server never issued must not be accepted."""
    client.cookies.set(OAUTH_STATE_COOKIE, "not-a-real-token")
    response = client.get(
        "/auth/google/callback?code=abc&state=attacker", follow_redirects=False
    )

    assert response.status_code == 400
    assert "state" in response.json()["detail"]


def test_callback_rejects_a_state_cookie_without_a_verifier(client):
    """A state token missing the PKCE claim cannot complete the exchange."""
    forged = get_session_codec().issue("some-state", STATE_AUDIENCE, STATE_TTL)
    client.cookies.set(OAUTH_STATE_COOKIE, forged)

    response = client.get(
        "/auth/google/callback?code=abc&state=some-state", follow_redirects=False
    )

    assert response.status_code == 400
    assert "verifier" in response.json()["detail"]
