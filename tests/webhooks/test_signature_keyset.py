"""Fetching and caching Google's public keyset.

Google rotates these keys every 30 days and publishes five enabled at a time,
so the cache has to be both effective and self-healing.
"""

import pytest

from server.webhooks.error import SignatureError
from server.webhooks.signature import SignatureVerifier
from tests.google_webhook import NOTIFICATION, Keyset, make_keypair, sign


def test_the_keyset_is_fetched_once_not_per_notification():
    signer, public_json = make_keypair()
    keyset = Keyset(public_json)
    verifier = SignatureVerifier(fetch=keyset)

    for _ in range(3):
        verifier.verify(sign(signer, NOTIFICATION), NOTIFICATION)

    assert keyset.fetches == 1


def test_a_rotated_key_is_picked_up_without_waiting_for_the_cache():
    """Keys rotate every 30 days; a rotation must not break the hot path."""
    old_signer, old_public = make_keypair()
    keyset = Keyset(old_public)
    verifier = SignatureVerifier(fetch=keyset)
    verifier.verify(sign(old_signer, NOTIFICATION), NOTIFICATION)
    assert keyset.fetches == 1

    new_signer, new_public = make_keypair()
    keyset.contents = new_public

    verifier.verify(sign(new_signer, NOTIFICATION), NOTIFICATION)

    assert keyset.fetches == 2


def test_the_cache_expires():
    signer, public_json = make_keypair()
    keyset = Keyset(public_json)
    now = [0.0]
    verifier = SignatureVerifier(fetch=keyset, cache_seconds=60, clock=lambda: now[0])

    verifier.verify(sign(signer, NOTIFICATION), NOTIFICATION)
    now[0] = 61.0
    verifier.verify(sign(signer, NOTIFICATION), NOTIFICATION)

    assert keyset.fetches == 2


def test_an_unreachable_keyset_is_reported_clearly():
    def explode(url):
        raise ConnectionError("dns failure")

    with pytest.raises(SignatureError, match="could not load"):
        SignatureVerifier(fetch=explode).verify("AAAA", NOTIFICATION)
