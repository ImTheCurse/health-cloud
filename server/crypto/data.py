"""Encrypting stored health values at rest."""

import os
import zlib

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from server.crypto.const import (
    AES_KEY_BYTES,
    AES_NONCE_BYTES,
    COMPRESSED_FLAG,
    DATA_HEADER_BYTES,
    DATA_KEY_VERSION,
    KEY_VERSION_MASK,
)


class DataCipher:
    """AES-256-GCM for stored measurement values, with optional compression.

    Each ciphertext is ``header || nonce || ciphertext``. The one-byte header
    carries the key version in its low seven bits and ``COMPRESSED_FLAG`` in its
    high bit, so every value says how to read it back.

    The header is passed to GCM as associated data, so flipping the compression
    flag or the key version fails to decrypt rather than misreading the value.
    Nothing ties a ciphertext to its row: the defence is against reading the
    database, not against rewriting it.

    Compression happens before encryption because ciphertext does not compress,
    and Postgres's own compression of large values would otherwise be lost.
    """

    def __init__(self, key: bytes, key_version: int = DATA_KEY_VERSION) -> None:
        if len(key) != AES_KEY_BYTES:
            raise ValueError(f"key must be {AES_KEY_BYTES} bytes, got {len(key)}")
        if not 0 < key_version <= KEY_VERSION_MASK:
            raise ValueError(f"key version must be 1-{KEY_VERSION_MASK}")
        self._aesgcm = AESGCM(key)
        self._key_version = key_version

    @classmethod
    def from_hex(cls, hex_key: str) -> "DataCipher":
        """Build from the hex string held in the environment.

        Generate one with: ``openssl rand -hex 32``
        """
        try:
            key = bytes.fromhex(hex_key)
        except ValueError as exc:
            raise ValueError("key must be hex encoded") from exc
        return cls(key)

    def encrypt(self, plaintext: bytes, *, compress: bool) -> bytes:
        """Encrypt ``plaintext``, zlib-compressing it first when ``compress``.

        Compression is the caller's choice per column: it shrinks a JSON payload
        by a third or more, and makes a three-byte scalar bigger.
        """
        header = bytes([self._key_version | (COMPRESSED_FLAG if compress else 0)])
        body = zlib.compress(plaintext) if compress else plaintext
        nonce = os.urandom(AES_NONCE_BYTES)
        return header + nonce + self._aesgcm.encrypt(nonce, body, header)

    def decrypt(self, payload: bytes) -> bytes:
        """The plaintext ``encrypt`` was given, decompressed if it was compressed.

        Raises:
            ValueError: the payload names a key this cipher does not hold.
            cryptography.exceptions.InvalidTag: the payload was altered, or was
                encrypted under a different key.
        """
        nonce_end = DATA_HEADER_BYTES + AES_NONCE_BYTES
        header = payload[:DATA_HEADER_BYTES]
        nonce = payload[DATA_HEADER_BYTES:nonce_end]
        ciphertext = payload[nonce_end:]
        if not header:
            raise ValueError("empty payload")

        key_version = header[0] & KEY_VERSION_MASK
        if key_version != self._key_version:
            raise ValueError(
                f"value is encrypted under key version {key_version}, "
                f"this cipher holds {self._key_version}"
            )

        body = self._aesgcm.decrypt(nonce, ciphertext, header)
        return zlib.decompress(body) if header[0] & COMPRESSED_FLAG else body
