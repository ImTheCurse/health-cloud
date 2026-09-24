"""Receiving a change pointer: verify the signature, acknowledge, do no work."""

import inspect

from server.api.webhooks import receive
from server.webhooks.const import SIGNATURE_HEADER, WEBHOOK_PATH
from tests.google_webhook import AUTH, NOTIFICATION, make_keypair, sign


def test_a_signed_notification_is_acknowledged_with_204(signer_and_client):
    signer, client = signer_and_client

    response = client.post(
        WEBHOOK_PATH,
        content=NOTIFICATION,
        headers={
            "Authorization": AUTH,
            SIGNATURE_HEADER: sign(signer, NOTIFICATION),
        },
    )

    assert response.status_code == 204
    assert response.content == b""


def test_an_unsigned_notification_is_refused(signer_and_client):
    _, client = signer_and_client

    response = client.post(
        WEBHOOK_PATH, content=NOTIFICATION, headers={"Authorization": AUTH}
    )

    assert response.status_code == 403


def test_a_forged_notification_is_refused(signer_and_client):
    """Correct secret, wrong signing key: the secret alone is not enough."""
    _, client = signer_and_client
    attacker, _ = make_keypair()

    response = client.post(
        WEBHOOK_PATH,
        content=NOTIFICATION,
        headers={
            "Authorization": AUTH,
            SIGNATURE_HEADER: sign(attacker, NOTIFICATION),
        },
    )

    assert response.status_code == 403


def test_a_body_altered_in_transit_is_refused(signer_and_client):
    signer, client = signer_and_client
    header = sign(signer, NOTIFICATION)
    altered = NOTIFICATION.replace(b'"user-1"', b'"user-2"')

    response = client.post(
        WEBHOOK_PATH,
        content=altered,
        headers={"Authorization": AUTH, SIGNATURE_HEADER: header},
    )

    assert response.status_code == 403


def test_unparseable_body_with_a_valid_secret_is_refused(signer_and_client):
    _, client = signer_and_client

    response = client.post(
        WEBHOOK_PATH, content=b"not json", headers={"Authorization": AUTH}
    )

    assert response.status_code == 403


def test_the_endpoint_is_sync_so_it_cannot_block_the_event_loop():
    """The raw body is read by an async dependency instead."""
    assert not inspect.iscoroutinefunction(receive)
