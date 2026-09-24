"""Verifying that a notification really came from Google.

Google signs the raw JSON body with ECDSA P-256 / SHA-256 and publishes the
matching public keys as a Tink keyset. Only public key material is involved, so
this needs no secret-access token -- unlike a keyset holding private keys.
"""

import base64
import logging
import time
from functools import lru_cache

import requests
import tink
from tink import signature as tink_signature

from server.webhooks.const import (
    HTTP_TIMEOUT_SECONDS,
    KEYSET_CACHE_SECONDS,
    KEYSET_URL,
)
from server.webhooks.error import SignatureError

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def signature_primitives_registered() -> bool:
    """Register Tink's signature primitives, once per process.

    Tink's registry is process-global, and registering twice is wasteful rather
    than harmful. The cache is the singleton: calling this is idempotent and
    cheap, so callers need not track whether it has run.
    """
    tink_signature.register()
    return True


class SignatureVerifier:
    """Checks the signature header against Google's published keyset.

    The keyset is cached, because fetching it on every notification would make
    Google's availability our own. A failed verification forces one refresh and
    a retry: keys rotate every 30 days, and a rotation landing inside the cache
    window would otherwise reject every genuine notification until the TTL
    expired.
    """

    def __init__(
        self,
        keyset_url: str = KEYSET_URL,
        cache_seconds: int = KEYSET_CACHE_SECONDS,
        fetch=None,
        clock=time.monotonic,
    ) -> None:
        self._keyset_url = keyset_url
        self._cache_seconds = cache_seconds
        self._fetch = fetch or self._fetch_over_https
        self._clock = clock
        self._primitive = None
        self._fetched_at = 0.0

    @staticmethod
    def _fetch_over_https(url: str) -> str:
        response = requests.get(url, timeout=HTTP_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.text

    def _load(self, force: bool = False):
        expired = self._clock() - self._fetched_at >= self._cache_seconds
        if self._primitive is None or force or expired:
            signature_primitives_registered()
            try:
                raw = self._fetch(self._keyset_url)
                handle = tink.json_proto_keyset_format.parse_without_secret(raw)
                self._primitive = handle.primitive(tink_signature.PublicKeyVerify)
            except Exception as exc:
                logger.warning(
                    "could not load signing keyset from %s: %s", self._keyset_url, exc
                )
                raise SignatureError(
                    f"could not load Google's signing keyset: {exc}"
                ) from exc
            self._fetched_at = self._clock()
        return self._primitive

    def verify(self, signature_header: str | None, payload: bytes) -> None:
        """Raise SignatureError unless the payload was signed by Google.

        ``payload`` must be the exact bytes received. Re-serialising parsed JSON
        changes whitespace and key order, and the signature would not match.
        """
        if not signature_header:
            raise SignatureError("missing signature header")

        try:
            signature = base64.b64decode(signature_header, validate=True)
        except Exception as exc:
            raise SignatureError("signature header is not valid base64") from exc

        try:
            self._load().verify(signature, payload)
            return
        except tink.TinkError as exc:
            # Expected when keys have rotated, so not yet an error. Neither the
            # payload nor the signature is logged: the payload carries health
            # data, and the signature is noise without it.
            logger.info("signature failed against cached keyset (%s); refreshing", exc)

        # Possibly a rotation we have not picked up yet. Refresh once, retry.
        try:
            self._load(force=True).verify(signature, payload)
        except tink.TinkError as exc:
            logger.warning("signature rejected after keyset refresh: %s", exc)
            raise SignatureError("signature does not match Google's keyset") from exc
