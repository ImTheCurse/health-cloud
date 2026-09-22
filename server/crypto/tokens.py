"""Encrypting OAuth tokens at rest."""

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from server.crypto.const import AES_KEY_BYTES, AES_NONCE_BYTES


class TokenCipher:
    """AES-256-GCM encryption for stored OAuth tokens.

    Each ciphertext is ``nonce || ciphertext``, with a fresh random nonce per
    call, so encrypting the same token twice never produces the same bytes.

    ``associated_data`` binds a ciphertext to its context -- we pass the
    health_user_id, so a refresh token copied into another user's row fails to
    decrypt instead of silently working.
    """

    def __init__(self, key: bytes) -> None:
        if len(key) != AES_KEY_BYTES:
            raise ValueError(
                f"key must be {AES_KEY_BYTES} bytes, got {len(key)}"
            )
        self._aesgcm = AESGCM(key)

    @classmethod
    def from_hex(cls, hex_key: str) -> "TokenCipher":
        """Build from the hex string held in the environment.

        Generate one with: ``openssl rand -hex 32``
        """
        try:
            key = bytes.fromhex(hex_key)
        except ValueError as exc:
            raise ValueError("key must be hex encoded") from exc
        return cls(key)

    def encrypt(self, plaintext: str, associated_data: str) -> bytes:
        nonce = os.urandom(AES_NONCE_BYTES)
        ciphertext = self._aesgcm.encrypt(
            nonce, plaintext.encode("utf-8"), associated_data.encode("utf-8")
        )
        return nonce + ciphertext

    def decrypt(self, payload: bytes, associated_data: str) -> str:
        nonce, ciphertext = payload[:AES_NONCE_BYTES], payload[AES_NONCE_BYTES:]
        plaintext = self._aesgcm.decrypt(
            nonce, ciphertext, associated_data.encode("utf-8")
        )
        return plaintext.decode("utf-8")
