"""What signature handling must never reveal.

Deliberately not a test that the verifier logs correctly -- its behaviour is
covered by the exceptions it raises in test_signature_verification.py and
test_signature_keyset.py. What is worth pinning down is the one thing those
tests cannot see: that a notification body, which carries health data, never
reaches a log line by any route.
"""

import pytest

from server.webhooks.error import SignatureError
from server.webhooks.signature import SignatureVerifier
from tests.conftest import logged_text
from tests.google_webhook import FAKE_HEALTH_USER_ID, Keyset, make_keypair, sign


def test_registration_runs_once_per_process():
    """The lru_cache is the singleton; calling it repeatedly is a no-op.

    Not about logging: it is here because it guards the cache, and Tink's
    registry is process-global.
    """
    from server.webhooks.signature import signature_primitives_registered

    signature_primitives_registered()
    before = signature_primitives_registered.cache_info()
    signature_primitives_registered()

    assert signature_primitives_registered.cache_info().hits == before.hits + 1
    assert signature_primitives_registered.cache_info().currsize == 1


def test_the_payload_is_never_logged(logs):
    """Notification bodies carry health data; they must not reach the log."""
    attacker_signer, _ = make_keypair()
    _, google_public = make_keypair()
    verifier = SignatureVerifier(fetch=Keyset(google_public))
    secret_payload = (
        b'{"healthUserId":"' + FAKE_HEALTH_USER_ID.encode() + b'","dataType":"sleep"}'
    )

    with pytest.raises(SignatureError):
        verifier.verify(sign(attacker_signer, secret_payload), secret_payload)

    assert logs, "nothing was logged, so this test would pass vacuously"
    revealed = logged_text(logs)
    assert FAKE_HEALTH_USER_ID not in revealed
    assert "sleep" not in revealed


def test_the_signature_itself_is_never_logged(logs):
    """The signature is the caller's credential for that body."""
    attacker_signer, _ = make_keypair()
    _, google_public = make_keypair()
    verifier = SignatureVerifier(fetch=Keyset(google_public))
    payload = b'{"dataType":"steps"}'
    header = sign(attacker_signer, payload)

    with pytest.raises(SignatureError):
        verifier.verify(header, payload)

    assert logs, "nothing was logged, so this test would pass vacuously"
    assert header not in logged_text(logs)
