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

# The structure below was taken from a live delivery, but every real value in
# it has been replaced with an invented one of the same form, to keep personal
# and account data out of the repository. What was substituted:
#
#   clientProvidedSubscriptionName  held the real GCP project number and
#                                   subscriber id, both readable by anyone
#                                   with the repo
#   recordId                        identified a real health record
#   the interval times              were a real sleep window, and the gap
#                                   between the physical and civil forms gave
#                                   away the timezone it happened in
#
# The shapes are preserved exactly -- digit counts, the auto-<project>-<id>-
# WEBHOOK_DATA_TYPE_<TYPE> pattern, the Z-suffixed physical time against the
# offset-free civil one -- because the parser is what these tests exercise.
FAKE_PROJECT_NUMBER = "000000000000"
FAKE_SUBSCRIBER_ID = "example-subscriber"
FAKE_RECORD_ID = "100000000000000000"


def _pointer(data_type="steps", operation="UPSERT", health_user_id="user-1"):
    """One change pointer, shaped as Google really sends it.

    The interval carries parallel representations of the same window: an
    absolute UTC one and the wall-clock time the user would have seen.
    """
    return {
        "version": "1",
        "clientProvidedSubscriptionName": (
            f"auto-{FAKE_PROJECT_NUMBER}-{FAKE_SUBSCRIBER_ID}"
            f"-WEBHOOK_DATA_TYPE_{data_type.upper()}"
        ),
        "healthUserId": health_user_id,
        "operation": operation,
        "dataType": data_type,
        "intervals": [
            {
                "physicalTimeInterval": {
                    "startTime": "2026-01-02T09:00:00Z",
                    "endTime": "2026-01-02T11:00:00Z",
                },
                "civilIso8601TimeInterval": {
                    "startTime": "2026-01-02T10:00:00",
                    "endTime": "2026-01-02T12:00:00",
                },
            }
        ],
        "recordId": FAKE_RECORD_ID,
    }


#: A delivery in Google's real shape: a JSON *array* of envelopes, each
#: wrapping a change pointer under "data". Getting this shape wrong is not
#: hypothetical -- the
#: first live notifications were refused with 403 because the fixture here
#: was a bare object, so every test passed against a payload Google never
#: sends. The values are never in the body; the server queries for those.
NOTIFICATION = json.dumps([{"data": _pointer()}]).encode()

#: Two pointers in one delivery, which Google batches.
BATCHED_NOTIFICATION = json.dumps(
    [{"data": _pointer("steps")}, {"data": _pointer("sleep")}]
).encode()

#: The single bare object shown in the documentation, still accepted.
BARE_NOTIFICATION = json.dumps(_pointer()).encode()

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
