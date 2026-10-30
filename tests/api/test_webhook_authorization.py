"""The shared secret on the receiver, checked before anything else happens.

Google's handshake deliberately sends an unauthorized request and requires a
401 or 403, so this check must run first and must not depend on the body.
"""

from server.webhooks.const import WEBHOOK_PATH
from tests.google_webhook import VERIFICATION


def test_an_unauthorized_request_returns_401(signer_and_client):
    """Google sends the handshake body with no credentials and requires 401/403.

    Answering 200 here fails subscriber creation with FAILED_PRECONDITION.
    """
    _, client = signer_and_client

    response = client.post(WEBHOOK_PATH, content=VERIFICATION)

    assert response.status_code == 401


def test_a_wrong_secret_is_rejected(signer_and_client):
    _, client = signer_and_client

    response = client.post(
        WEBHOOK_PATH, content=VERIFICATION, headers={"Authorization": "Bearer wrong"}
    )

    assert response.status_code == 401


def test_authorization_is_checked_before_the_body_is_parsed(signer_and_client):
    """Garbage with no credentials must still answer 401, not 400 or 500.

    The handshake's challenge depends on this ordering.
    """
    _, client = signer_and_client

    response = client.post(WEBHOOK_PATH, content=b"not json at all")

    assert response.status_code == 401


def test_a_non_ascii_authorization_header_is_refused_not_crashed(signer_and_client):
    """Regression: a raw byte >= 0x80 must answer 401, not raise.

    Header values reach the app decoded as latin-1, and hmac.compare_digest
    refuses non-ASCII str operands, so comparing strings turned an
    unauthenticated probe into an unhandled TypeError and a 500.
    """
    _, client = signer_and_client

    response = client.post(
        WEBHOOK_PATH,
        content=VERIFICATION,
        headers={"Authorization": b"Bearer \xff"},
    )

    assert response.status_code == 401
