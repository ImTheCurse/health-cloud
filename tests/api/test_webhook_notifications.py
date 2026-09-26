"""Receiving a change pointer: verify the signature, acknowledge, do no work."""

from server.webhooks.const import SIGNATURE_HEADER, WEBHOOK_PATH
from tests.conftest import logged_text
from tests.google_webhook import (
    AUTH,
    BATCHED_NOTIFICATION,
    FAKE_HEALTH_USER_ID,
    FAKE_RECORD_ID,
    NOTIFICATION,
    SECRET,
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
    altered = NOTIFICATION.replace(
        FAKE_HEALTH_USER_ID.encode(), b"9" * len(FAKE_HEALTH_USER_ID)
    )
    assert altered != NOTIFICATION, "the body was not actually altered"

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


def test_a_batched_delivery_is_acknowledged(signer_and_client):
    """Google batches several pointers into one delivery."""
    signer, client = signer_and_client

    response = client.post(
        WEBHOOK_PATH,
        content=BATCHED_NOTIFICATION,
        headers={
            "Authorization": AUTH,
            SIGNATURE_HEADER: sign(signer, BATCHED_NOTIFICATION),
        },
    )

    assert response.status_code == 204


def test_a_signed_body_we_cannot_parse_is_refused(signer_and_client):
    """A valid signature over a body our parser rejects still must not 500."""
    signer, client = signer_and_client
    unreadable = b'{"unexpected": "shape", "data": "not an object"}'

    response = client.post(
        WEBHOOK_PATH,
        content=unreadable,
        headers={
            "Authorization": AUTH,
            SIGNATURE_HEADER: sign(signer, unreadable),
        },
    )

    assert response.status_code == 403


def test_the_notification_body_never_reaches_a_log(signer_and_client, logs):
    """The delivery is health data; only the shape of it may be logged.

    The request line records what changed -- operation, data type, how many
    intervals -- and the hashed user. The record id, the timestamps and the
    raw body must not appear anywhere in it.
    """
    signer, client = signer_and_client

    client.post(
        WEBHOOK_PATH,
        content=NOTIFICATION,
        headers={
            "Authorization": AUTH,
            SIGNATURE_HEADER: sign(signer, NOTIFICATION),
        },
    )

    assert logs, "nothing was logged, so this test would pass vacuously"
    revealed = logged_text(logs)
    assert FAKE_RECORD_ID not in revealed
    assert "2026-01-02T09:00:00Z" not in revealed
    assert FAKE_HEALTH_USER_ID not in revealed, "the health user id must be hashed"


def test_the_shared_secret_never_reaches_a_log(signer_and_client, logs):
    """It is replayed on every delivery; a log is the likeliest place to leak it."""
    signer, client = signer_and_client

    client.post(
        WEBHOOK_PATH,
        content=NOTIFICATION,
        headers={
            "Authorization": AUTH,
            SIGNATURE_HEADER: sign(signer, NOTIFICATION),
        },
    )

    assert logs, "nothing was logged, so this test would pass vacuously"
    revealed = logged_text(logs)
    assert SECRET not in revealed
    assert AUTH not in revealed
