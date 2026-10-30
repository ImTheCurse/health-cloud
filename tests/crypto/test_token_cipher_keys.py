"""Key material the cipher refuses to be built from.

TOKEN_ENCRYPTION_KEY comes straight from the environment, so a typo must fail
at construction rather than at the first decrypt.
"""

import pytest

from server.crypto.tokens import TokenCipher


def test_key_must_be_the_right_length():
    with pytest.raises(ValueError, match="32 bytes"):
        TokenCipher(b"too-short")


def test_key_must_be_hex():
    with pytest.raises(ValueError, match="hex"):
        TokenCipher.from_hex("nonsense!")
