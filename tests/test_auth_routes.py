from urllib.parse import parse_qs, urlparse

from server.auth.const import (
    OAUTH_STATE_COOKIE,
    SESSION_COOKIE,
    STATE_AUDIENCE,
    STATE_TTL,
)
from server.providers import get_session_codec


def test_login_redirects_to_google_and_sets_a_state_cookie(client):
    response = client.get("/auth/google/login", follow_redirects=False)

    assert response.status_code == 307
    location = urlparse(response.headers["location"])
    assert location.netloc == "accounts.google.com"

    params = parse_qs(location.query)
    assert params["access_type"] == ["offline"]
    assert params["prompt"] == ["consent"]

    # The state in the URL must match the signed state cookie, or the callback
    # has no CSRF defence.
    state_cookie = response.cookies[OAUTH_STATE_COOKIE]
    assert get_session_codec().verify(state_cookie, STATE_AUDIENCE) == params["state"][0]


def test_login_requests_read_only_health_scopes(client):
    response = client.get("/auth/google/login", follow_redirects=False)
    scopes = parse_qs(urlparse(response.headers["location"]).query)["scope"][0].split()

    health_scopes = [s for s in scopes if "googlehealth" in s]
    assert len(health_scopes) == 9
    assert all(s.endswith(".readonly") for s in health_scopes)
    assert not any(".writeonly" in s for s in scopes)


def test_state_cookie_is_httponly(client):
    response = client.get("/auth/google/login", follow_redirects=False)

    set_cookie = response.headers["set-cookie"]
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()


def test_me_requires_a_session(client):
    assert client.get("/auth/me").status_code == 401


def test_status_requires_a_session(client):
    assert client.get("/auth/status").status_code == 401


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


def test_logout_clears_the_session_cookie(client):
    response = client.post("/auth/logout")

    assert response.status_code == 200
    assert SESSION_COOKIE in response.headers["set-cookie"]


def test_login_sends_a_pkce_challenge_and_keeps_the_verifier(client):
    """PKCE: Google gets the challenge, the cookie keeps the verifier.

    Regression test. Rebuilding the Flow at the callback loses the verifier and
    Google rejects the exchange with `invalid_grant: Missing code verifier`.
    """
    from server.auth.const import CODE_VERIFIER_CLAIM

    response = client.get("/auth/google/login", follow_redirects=False)
    params = parse_qs(urlparse(response.headers["location"]).query)

    assert params["code_challenge_method"] == ["S256"]
    assert params["code_challenge"][0]

    claims = get_session_codec().verify_claims(
        response.cookies[OAUTH_STATE_COOKIE], STATE_AUDIENCE
    )
    verifier = claims[CODE_VERIFIER_CLAIM]

    assert verifier
    # The verifier itself must never travel to Google in the redirect.
    assert verifier not in response.headers["location"]


def test_callback_rejects_a_state_cookie_without_a_verifier(client):
    """A state token missing the PKCE claim cannot complete the exchange."""
    forged = get_session_codec().issue("some-state", STATE_AUDIENCE, STATE_TTL)
    client.cookies.set(OAUTH_STATE_COOKIE, forged)

    response = client.get(
        "/auth/google/callback?code=abc&state=some-state", follow_redirects=False
    )

    assert response.status_code == 400
    assert "verifier" in response.json()["detail"]
