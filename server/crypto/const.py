"""Cryptographic constants.

Tink is deliberately absent here: it is used only to verify Google's webhook
signatures, where Google publishes a public Tink keyset that needs no
secret key material. Secrets of our own use `cryptography` and PyJWT, so no
Tink keysets and no secret-access tokens are involved.
"""

from typing import Final

#: AES-256-GCM.
AES_KEY_BYTES: Final = 32

#: 96-bit nonce, the size AES-GCM is specified for. Prepended to each ciphertext.
AES_NONCE_BYTES: Final = 12

#: Pinned on both encode and decode so a token cannot claim a weaker algorithm.
SESSION_ALGORITHM: Final = "HS256"
