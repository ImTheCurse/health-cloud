"""Google's verification handshake, which subscriber creation depends on.

The unauthorized half of the handshake lives in the authorization tests.
"""

import json

from server.webhooks.const import VERIFICATION_TYPE, WEBHOOK_PATH
from tests.google_webhook import AUTH, NOTIFICATION, VERIFICATION


def test_an_authorized_verification_returns_200(signer_and_client):
    _, client = signer_and_client

    response = client.post(
        WEBHOOK_PATH, content=VERIFICATION, headers={"Authorization": AUTH}
    )

    assert response.status_code == 200


def test_the_verification_body_needs_no_signature(signer_and_client):
    """Google does not sign the handshake, so requiring one would break it."""
    _, client = signer_and_client

    response = client.post(
        WEBHOOK_PATH, content=VERIFICATION, headers={"Authorization": AUTH}
    )

    assert response.status_code == 200


def test_a_change_pointer_wearing_the_handshake_marker_is_refused(signer_and_client):
    """Regression: the handshake is the one branch that skips the signature.

    Matching any body that merely *contained* type=verification let a caller
    holding the shared secret attach the marker to a change pointer and be
    answered 200 with no signature at all, collapsing the two-factor check to
    secret-only. The match is exact now, so this is a notification like any
    other and fails on its missing signature.
    """
    _, client = signer_and_client
    disguised = json.dumps(
        {**json.loads(NOTIFICATION), "type": VERIFICATION_TYPE}
    ).encode()

    response = client.post(
        WEBHOOK_PATH, content=disguised, headers={"Authorization": AUTH}
    )

    assert response.status_code == 403
