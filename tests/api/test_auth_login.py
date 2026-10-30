"""Starting consent: the redirect to Google and the state cookie that guards it."""

from urllib.parse import parse_qs, urlparse

from server.auth.const import CODE_VERIFIER_CLAIM, OAUTH_STATE_COOKIE, STATE_AUDIENCE
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


def test_login_sends_a_pkce_challenge_and_keeps_the_verifier(client):
    """PKCE: Google gets the challenge, the cookie keeps the verifier.

    Regression test. Rebuilding the Flow at the callback loses the verifier and
    Google rejects the exchange with `invalid_grant: Missing code verifier`.
    """
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
