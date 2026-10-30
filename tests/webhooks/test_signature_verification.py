"""Accepting Google's signature and rejecting everything else."""

import pytest

from server.webhooks.error import SignatureError
from server.webhooks.signature import SignatureVerifier
from tests.google_webhook import NOTIFICATION, Keyset, make_keypair, sign


def test_a_genuine_signature_verifies():
    signer, public_json = make_keypair()
    verifier = SignatureVerifier(fetch=Keyset(public_json))

    verifier.verify(sign(signer, NOTIFICATION), NOTIFICATION)


def test_a_tampered_payload_is_rejected():
    signer, public_json = make_keypair()
    verifier = SignatureVerifier(fetch=Keyset(public_json))
    header = sign(signer, NOTIFICATION)

    with pytest.raises(SignatureError, match="does not match"):
        verifier.verify(header, NOTIFICATION + b" ")


def test_a_signature_from_another_key_is_rejected():
    """The exact shape of a forged notification."""
    attacker_signer, _ = make_keypair()
    _, google_public = make_keypair()
    verifier = SignatureVerifier(fetch=Keyset(google_public))

    with pytest.raises(SignatureError):
        verifier.verify(sign(attacker_signer, NOTIFICATION), NOTIFICATION)


def test_a_missing_signature_is_rejected():
    _, public_json = make_keypair()

    with pytest.raises(SignatureError, match="missing signature"):
        SignatureVerifier(fetch=Keyset(public_json)).verify(None, NOTIFICATION)


def test_a_non_base64_signature_is_rejected():
    _, public_json = make_keypair()

    with pytest.raises(SignatureError, match="base64"):
        SignatureVerifier(fetch=Keyset(public_json)).verify("not base64!", NOTIFICATION)
