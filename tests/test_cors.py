from server.config.settings import get_settings

ALLOWED = get_settings().allowed_origins[0]


def test_allowed_origin_may_send_credentials(client):
    response = client.get("/auth/status", headers={"Origin": ALLOWED})

    assert response.headers["access-control-allow-origin"] == ALLOWED
    assert response.headers["access-control-allow-credentials"] == "true"


def test_unknown_origin_gets_no_allow_origin_header(client):
    """Without this header the browser refuses to hand over the response."""
    response = client.get("/auth/status", headers={"Origin": "http://evil.example"})

    assert "access-control-allow-origin" not in response.headers


def test_preflight_permits_the_logout_post(client):
    response = client.options(
        "/auth/logout",
        headers={
            "Origin": ALLOWED,
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert "POST" in response.headers["access-control-allow-methods"]
