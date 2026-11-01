"""Column types that encrypt a value on its way into Postgres.

A model field keeps its Python type -- ``dict``, ``Decimal``, ``str`` -- and the
column stores ``bytea``. Encryption happens when SQLAlchemy binds a parameter and
decryption when it reads a result, so the upsert, the ORM and Core statements all
pass through it without knowing.

**An encrypted column cannot be compared in SQL.** Every encryption draws a fresh
nonce, so ``WHERE value_unit = 'kg'`` encrypts ``'kg'`` anew and matches nothing.
Filter on the plaintext structure columns and compare values in Python.

**Select only the columns a read needs.** Loading a whole row decrypts and
decompresses ``raw`` with it.

``TypeDecorator`` and ``LargeBinary`` are imported from SQLAlchemy because
SQLModel re-exports neither.
"""

import json
from decimal import Decimal
from typing import Any

from sqlalchemy import LargeBinary
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

from server.crypto.data import DataCipher


def _cipher() -> DataCipher:
    # Imported here, not at module level: the providers import the fetcher, which
    # imports these models, and the key must not be read when a model is defined.
    from server.providers import get_data_cipher

    return get_data_cipher()


class _Encrypted(TypeDecorator[Any]):
    """Encrypts the bytes ``_encode`` produces; decrypts and ``_decode``s them.

    ``None`` stays SQL NULL rather than becoming an encrypted empty value, so a
    ``NOT NULL`` column still refuses a row with nothing in it.

    Each subclass sets ``cache_ok``: SQLAlchemy reads it from the class itself,
    not from a base, and without it no statement using the type is cached.
    """

    impl = LargeBinary

    #: zlib before encrypting. Worth it for JSON; a short scalar only grows.
    compress = False

    def process_bind_param(self, value: Any, dialect: Dialect) -> bytes | None:
        if value is None:
            return None
        return _cipher().encrypt(self._encode(value), compress=self.compress)

    def process_result_value(self, value: bytes | None, dialect: Dialect) -> Any:
        if value is None:
            return None
        return self._decode(_cipher().decrypt(bytes(value)))

    def _encode(self, value: Any) -> bytes:
        raise NotImplementedError

    def _decode(self, plaintext: bytes) -> Any:
        raise NotImplementedError


class EncryptedJSON(_Encrypted):
    """A JSON document, compressed and encrypted.

    Serialised compactly: the separators JSON adds for readability are bytes
    stored for every row.
    """

    cache_ok = True
    compress = True

    def _encode(self, value: Any) -> bytes:
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()

    def _decode(self, plaintext: bytes) -> Any:
        return json.loads(plaintext)


class EncryptedDecimal(_Encrypted):
    """A number, stored as its exact decimal string so no precision is lost."""

    cache_ok = True

    def _encode(self, value: Any) -> bytes:
        return str(Decimal(value)).encode()

    def _decode(self, plaintext: bytes) -> Decimal:
        return Decimal(plaintext.decode())


class EncryptedText(_Encrypted):
    """A short string: a unit, a sleep stage name."""

    cache_ok = True

    def _encode(self, value: Any) -> bytes:
        return str(value).encode()

    def _decode(self, plaintext: bytes) -> str:
        return plaintext.decode()
