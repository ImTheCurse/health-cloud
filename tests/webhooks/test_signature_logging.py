"""What signature handling writes to the log, and what it must never write.

A first-attempt failure is routine during a key rotation; a failure after the
refresh is not. The levels have to tell those apart, and neither may carry the
notification body, which holds health data.
"""

import pytest

from server.webhooks.error import SignatureError
from server.webhooks.signature import SignatureVerifier
from tests.google_webhook import NOTIFICATION, Keyset, make_keypair, sign


def test_registration_runs_once_per_process():
    """The lru_cache is the singleton; calling it repeatedly is a no-op."""
    from server.webhooks.signature import signature_primitives_registered

    signature_primitives_registered()
    before = signature_primitives_registered.cache_info()
    signature_primitives_registered()

    assert signature_primitives_registered.cache_info().hits == before.hits + 1
    assert signature_primitives_registered.cache_info().currsize == 1


def test_a_rotation_is_logged_as_information_not_an_error(caplog):
    old_signer, old_public = make_keypair()
    keyset = Keyset(old_public)
    verifier = SignatureVerifier(fetch=keyset)
    verifier.verify(sign(old_signer, NOTIFICATION), NOTIFICATION)

    new_signer, new_public = make_keypair()
    keyset.contents = new_public

    with caplog.at_level("INFO", logger="server.webhooks.signature"):
        verifier.verify(sign(new_signer, NOTIFICATION), NOTIFICATION)

    assert "refreshing" in caplog.text
    assert not [r for r in caplog.records if r.levelname in {"WARNING", "ERROR"}]


def test_a_rejected_signature_is_logged_as_a_warning(caplog):
    attacker_signer, _ = make_keypair()
    _, google_public = make_keypair()
    verifier = SignatureVerifier(fetch=Keyset(google_public))

    with caplog.at_level("INFO", logger="server.webhooks.signature"):
        with pytest.raises(SignatureError):
            verifier.verify(sign(attacker_signer, NOTIFICATION), NOTIFICATION)

    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert warnings, "a rejected signature should be visible in the log"
    assert "after keyset refresh" in warnings[0].getMessage()


def test_the_payload_is_never_logged(caplog):
    """Notification bodies carry health data; they must not reach the log."""
    attacker_signer, _ = make_keypair()
    _, google_public = make_keypair()
    verifier = SignatureVerifier(fetch=Keyset(google_public))
    secret_payload = b'{"healthUserId":"user-1","dataType":"sleep"}'

    with caplog.at_level("DEBUG", logger="server.webhooks.signature"):
        with pytest.raises(SignatureError):
            verifier.verify(sign(attacker_signer, secret_payload), secret_payload)

    assert "user-1" not in caplog.text
    assert "sleep" not in caplog.text


def test_an_unreachable_keyset_is_logged(caplog):
    def explode(url):
        raise ConnectionError("dns failure")

    with caplog.at_level("WARNING", logger="server.webhooks.signature"):
        with pytest.raises(SignatureError):
            SignatureVerifier(fetch=explode).verify("AAAA", NOTIFICATION)

    assert "could not load signing keyset" in caplog.text
