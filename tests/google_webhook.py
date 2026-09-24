"""Test doubles for Google's webhook: throwaway signing keys and sample bodies.

Google's private keys are unavailable, so tests sign with a keypair they
generate themselves and serve its public half as the keyset. Shared by the
signature unit tests and the endpoint tests, which both need a genuine
signature over a body Google would plausibly send.
"""

import base64
import json

import tink
from tink import signature as tink_signature

from server.webhooks.const import authorization_value

#: The shared secret the receiver is configured with in tests, and the exact
#: header value Google would send back, built the same way the subscriber
#: registration builds it.
SECRET = "test-secret"
AUTH = authorization_value(SECRET)

#: A change pointer, the only thing Google's webhook delivers. The values are
#: never fetched from here -- the server queries the Health API for those.
NOTIFICATION = json.dumps(
    {
        "version": "1",
        "clientProvidedSubscriptionName": "sub",
        "healthUserId": "user-1",
        "operation": "UPSERT",
        "dataType": "steps",
        "intervals": [],
    }
).encode()

#: The handshake body, sent twice during subscriber creation: once with
#: credentials and once without.
VERIFICATION = json.dumps({"type": "verification"}).encode()


def make_keypair():
    """Return a signer and the matching public keyset as Google serves it."""
    tink_signature.register()
    private = tink.new_keyset_handle(tink_signature.signature_key_templates.ECDSA_P256)
    public_json = tink.json_proto_keyset_format.serialize_without_secret(
        private.public_keyset_handle()
    )
    return private.primitive(tink_signature.PublicKeySign), public_json


def sign(signer, payload: bytes) -> str:
    """Sign a body and encode it the way the signature header carries it."""
    return base64.b64encode(signer.sign(payload)).decode()


class Keyset:
    """Serves a keyset and counts fetches, so caching can be asserted."""

    def __init__(self, contents):
        self.contents = contents
        self.fetches = 0

    def __call__(self, url):
        self.fetches += 1
        return self.contents
