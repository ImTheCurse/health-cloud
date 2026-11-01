"""The cipher for stored health values, against throwaway keys."""

import json
import secrets

import pytest
from cryptography.exceptions import InvalidTag

from server.crypto.const import (
    AES_KEY_BYTES,
    AES_NONCE_BYTES,
    AES_TAG_BYTES,
    COMPRESSED_FLAG,
    DATA_HEADER_BYTES,
    DATA_KEY_VERSION,
)
from server.crypto.data import DataCipher

#: A heart-rate reading: the short scalar an uncompressed column holds.
SCALAR = b"72"

#: How many sleep stages the large payload carries -- a typical night.
STAGES_PER_NIGHT = 80

#: A sleep-sized payload: repetitive JSON, which is what compression is for.
PAYLOAD = json.dumps(
    {
        "stages": [
            {"type": "LIGHT", "startTime": "2026-01-02T01:00:00Z"}
            for _ in range(STAGES_PER_NIGHT)
        ]
    }
).encode()

#: The least JSON compression must save to be worth doing -- half.
MIN_COMPRESSION_RATIO = 2

#: Flipping one bit is the smallest possible edit to a stored value.
ONE_BIT = 0b1


@pytest.fixture
def cipher() -> DataCipher:
    return DataCipher(secrets.token_bytes(AES_KEY_BYTES))


@pytest.mark.parametrize("compress", [True, False])
def test_a_value_round_trips(cipher, compress):
    assert cipher.decrypt(cipher.encrypt(PAYLOAD, compress=compress)) == PAYLOAD


def test_the_header_names_the_key_and_the_compression(cipher):
    assert cipher.encrypt(SCALAR, compress=False)[0] == DATA_KEY_VERSION
    assert (
        cipher.encrypt(SCALAR, compress=True)[0] == DATA_KEY_VERSION | COMPRESSED_FLAG
    )


def test_an_uncompressed_value_costs_exactly_the_fixed_overhead(cipher):
    """Header, nonce and tag are added; AES-GCM itself adds no padding."""
    overhead = DATA_HEADER_BYTES + AES_NONCE_BYTES + AES_TAG_BYTES

    assert len(cipher.encrypt(SCALAR, compress=False)) == len(SCALAR) + overhead


def test_compression_shrinks_a_large_payload(cipher):
    compressed = cipher.encrypt(PAYLOAD, compress=True)
    plain = cipher.encrypt(PAYLOAD, compress=False)

    assert len(compressed) * MIN_COMPRESSION_RATIO < len(plain)


def test_the_plaintext_does_not_appear_in_the_ciphertext(cipher):
    for compress in (True, False):
        assert b"LIGHT" not in cipher.encrypt(PAYLOAD, compress=compress)


def test_the_same_value_encrypts_differently_each_time(cipher):
    """Equal readings must not produce equal bytes.

    AES-GCM is deterministic for a given key, nonce and plaintext; what makes
    the output differ is that ``encrypt`` draws a fresh random nonce per call.
    Were the nonce fixed, every 72 bpm would be stored as the same bytes, and a
    reader of the database could count repeats and match rows by value without
    decrypting anything. (Reusing a nonce under one key also breaks GCM outright.)
    """
    first = cipher.encrypt(SCALAR, compress=False)
    second = cipher.encrypt(SCALAR, compress=False)

    assert first != second
    assert cipher.decrypt(first) == cipher.decrypt(second) == SCALAR


def test_a_tampered_ciphertext_is_rejected(cipher):
    payload = bytearray(cipher.encrypt(SCALAR, compress=False))
    payload[-1] ^= ONE_BIT  # inside the GCM tag

    with pytest.raises(InvalidTag):
        cipher.decrypt(bytes(payload))


def test_a_flipped_compression_flag_is_rejected(cipher):
    """The header is authenticated: readable, but not editable.

    The header cannot be encrypted -- ``decrypt`` must read the key version
    before it knows which key to use. So it is stored in the clear, and passed
    to AES-GCM as *associated data*: bytes that are not encrypted but are
    covered by the authentication tag, exactly as the ciphertext is. Changing
    any of them makes the tag check fail.

    Without that, flipping the compression bit would make ``decrypt`` hand a
    plain value to zlib, or return compressed bytes as if they were the value.
    With it, the edit is caught before any byte is interpreted.
    """
    payload = bytearray(cipher.encrypt(PAYLOAD, compress=True))
    payload[0] ^= COMPRESSED_FLAG

    with pytest.raises(InvalidTag):
        cipher.decrypt(bytes(payload))


def test_another_key_cannot_decrypt(cipher):
    other = DataCipher(secrets.token_bytes(AES_KEY_BYTES))

    with pytest.raises(InvalidTag):
        other.decrypt(cipher.encrypt(SCALAR, compress=False))


def test_a_value_under_an_unknown_key_version_is_refused(cipher):
    rotated_version = DATA_KEY_VERSION + 1
    rotated = DataCipher(secrets.token_bytes(AES_KEY_BYTES), key_version=rotated_version)

    with pytest.raises(ValueError, match=f"key version {rotated_version}"):
        cipher.decrypt(rotated.encrypt(SCALAR, compress=False))


def test_a_short_key_is_refused():
    with pytest.raises(ValueError, match=f"{AES_KEY_BYTES} bytes"):
        DataCipher(secrets.token_bytes(AES_KEY_BYTES - 1))


def test_a_hex_key_is_accepted():
    cipher = DataCipher.from_hex(secrets.token_hex(AES_KEY_BYTES))

    assert cipher.decrypt(cipher.encrypt(SCALAR, compress=False)) == SCALAR


def test_a_non_hex_key_is_refused():
    with pytest.raises(ValueError, match="hex"):
        DataCipher.from_hex("not hex")
