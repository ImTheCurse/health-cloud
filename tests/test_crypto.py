import secrets

import pytest
from cryptography.exceptions import InvalidTag

from server.crypto.const import AES_KEY_BYTES
from server.crypto.tokens import TokenCipher


@pytest.fixture
def cipher() -> TokenCipher:
    """Built from a throwaway key, with no environment involved."""
    return TokenCipher.from_hex(secrets.token_hex(AES_KEY_BYTES))


def test_token_round_trips(cipher):
    ciphertext = cipher.encrypt("refresh-token-value", "user-123")

    assert cipher.decrypt(ciphertext, "user-123") == "refresh-token-value"


def test_ciphertext_is_not_the_plaintext(cipher):
    assert b"refresh-token-value" not in cipher.encrypt("refresh-token-value", "user-1")


def test_ciphertext_is_bound_to_its_user(cipher):
    """Associated data means a token copied into another row will not decrypt."""
    ciphertext = cipher.encrypt("refresh-token-value", "user-123")

    with pytest.raises(InvalidTag):
        cipher.decrypt(ciphertext, "user-456")


def test_encryption_is_randomised(cipher):
    assert cipher.encrypt("same", "user-123") != cipher.encrypt("same", "user-123")


def test_tampered_ciphertext_is_rejected(cipher):
    ciphertext = bytearray(cipher.encrypt("refresh-token-value", "user-123"))
    ciphertext[-1] ^= 0x01

    with pytest.raises(InvalidTag):
        cipher.decrypt(bytes(ciphertext), "user-123")


def test_key_must_be_the_right_length():
    with pytest.raises(ValueError, match="32 bytes"):
        TokenCipher(b"too-short")


def test_key_must_be_hex():
    with pytest.raises(ValueError, match="hex"):
        TokenCipher.from_hex("nonsense!")
