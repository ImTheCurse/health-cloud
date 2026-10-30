"""Routes that read or clear the session cookie."""

from server.auth.const import SESSION_COOKIE


def test_me_requires_a_session(client):
    assert client.get("/auth/me").status_code == 401


def test_status_requires_a_session(client):
    assert client.get("/auth/status").status_code == 401


def test_logout_clears_the_session_cookie(client):
    response = client.post("/auth/logout")

    assert response.status_code == 200
    assert SESSION_COOKIE in response.headers["set-cookie"]
