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

#: The authentication tag AES-GCM appends to every ciphertext.
AES_TAG_BYTES: Final = 16

#: Pinned on both encode and decode so a token cannot claim a weaker algorithm.
SESSION_ALGORITHM: Final = "HS256"

#: The key a stored health value is encrypted under. One key exists; the number
#: is written into every ciphertext so a rotated key can still read old rows.
DATA_KEY_VERSION: Final = 1

#: A stored health value starts with one header byte, before the nonce.
DATA_HEADER_BYTES: Final = 1

#: The header byte's high bit: set when the plaintext was zlib-compressed before
#: encryption. The low seven bits are the key version.
COMPRESSED_FLAG: Final = 0x80
KEY_VERSION_MASK: Final = 0x7F
