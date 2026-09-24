"""Receiving a change pointer: verify the signature, acknowledge, do no work."""

import inspect

from server.api.webhooks import receive
from server.webhooks.const import SIGNATURE_HEADER, WEBHOOK_PATH
from tests.google_webhook import (
    AUTH,
    BATCHED_NOTIFICATION,
    NOTIFICATION,
    make_keypair,
    sign,
)


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


def test_a_verified_notification_is_logged(signer_and_client, caplog):
    """Until persistence lands the log is the only record of a delivery.

    If this stops firing, an empty log during step 4 would be ambiguous: no
    notification, or no logging?
    """
    signer, client = signer_and_client

    with caplog.at_level("INFO", logger="server.api.webhooks"):
        client.post(
            WEBHOOK_PATH,
            content=NOTIFICATION,
            headers={
                "Authorization": AUTH,
                SIGNATURE_HEADER: sign(signer, NOTIFICATION),
            },
        )

    assert "UPSERT" in caplog.text
    assert "steps" in caplog.text


def test_a_refused_notification_is_not_logged_as_received(signer_and_client, caplog):
    """A forged body must not appear in the log as though it arrived cleanly."""
    _, client = signer_and_client
    attacker, _ = make_keypair()

    with caplog.at_level("INFO", logger="server.api.webhooks"):
        client.post(
            WEBHOOK_PATH,
            content=NOTIFICATION,
            headers={
                "Authorization": AUTH,
                SIGNATURE_HEADER: sign(attacker, NOTIFICATION),
            },
        )

    assert "notification:" not in caplog.text


def test_every_pointer_in_a_batched_delivery_is_logged(signer_and_client, caplog):
    """Google batches several pointers into one delivery; none may be dropped."""
    signer, client = signer_and_client

    with caplog.at_level("INFO", logger="server.api.webhooks"):
        response = client.post(
            WEBHOOK_PATH,
            content=BATCHED_NOTIFICATION,
            headers={
                "Authorization": AUTH,
                SIGNATURE_HEADER: sign(signer, BATCHED_NOTIFICATION),
            },
        )

    assert response.status_code == 204
    assert caplog.text.count("notification:") == 2
    assert "steps" in caplog.text and "sleep" in caplog.text


def test_a_signed_body_we_cannot_parse_is_logged_loudly(signer_and_client, caplog):
    """Regression: this exact case failed silently.

    A valid signature over a body our parser rejects means the parser is
    wrong. It returned a bare 403 with nothing in the log, which is
    indistinguishable from a forged notification -- and that is precisely what
    disguised the payload-shape mismatch when real traffic first arrived.
    """
    signer, client = signer_and_client
    unreadable = b'{"unexpected": "shape", "data": "not an object"}'

    with caplog.at_level("INFO", logger="server.api.webhooks"):
        response = client.post(
            WEBHOOK_PATH,
            content=unreadable,
            headers={
                "Authorization": AUTH,
                SIGNATURE_HEADER: sign(signer, unreadable),
            },
        )

    assert response.status_code == 403
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert warnings, "a signed body we cannot parse must not fail silently"
    assert "could not be parsed" in warnings[0].getMessage()
