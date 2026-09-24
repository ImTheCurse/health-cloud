"""Deciding what to do with an inbound request from Google.

Two different requests arrive on the same path:

- the verification handshake, posted when a subscriber is created or repointed
- real notifications, each signed and carrying a change pointer

Kept free of FastAPI so the decision logic can be tested directly.
"""

import hmac
import json

from server.webhooks.const import VERIFICATION_TYPE
from server.webhooks.error import NotificationError


class EndpointAuthorizer:
    """Checks the Authorization header Google replays on every request.

    The secret is whatever string was registered with the subscriber, compared
    in constant time because this runs on a publicly reachable path.
    """

    def __init__(self, expected: str) -> None:
        if not expected:
            raise ValueError("webhook authorization secret must not be empty")
        # Compared as bytes: compare_digest refuses non-ASCII str operands, and
        # header values reach us decoded as latin-1, so a single byte >= 0x80
        # from anyone on the internet would raise TypeError and 500 instead of
        # answering 401. Encoding both sides keeps the comparison constant time.
        self._expected = expected.encode("utf-8", "surrogateescape")

    def authorized(self, header: str | None) -> bool:
        if not header:
            return False
        return hmac.compare_digest(
            header.encode("utf-8", "surrogateescape"), self._expected
        )


def is_verification_request(body: bytes) -> bool:
    """True when this is the handshake, not a notification.

    Google posts exactly ``{"type": "verification"}``, and the match here is
    exact for a reason: this is the one branch that answers without checking
    the signature. Accepting any body that merely *contains* that key would let
    a caller holding the shared secret attach it to a change pointer and skip
    signature verification altogether -- the signature is the second factor,
    and the secret alone must not be enough.

    A body we cannot parse is not a verification request; the signature check
    will reject it in a moment.
    """
    try:
        payload = json.loads(body)
    except (ValueError, TypeError):
        return False
    return payload == {"type": VERIFICATION_TYPE}


def parse_notification(body: bytes) -> list[dict]:
    """Unwrap the change pointers a verified notification carries.

    Google delivers a JSON *array* of envelopes, each holding the pointer
    under a ``data`` key, and one delivery can batch several::

        [{"data": {"version": "1", "dataType": "sleep", "intervals": [...]}}]

    A bare object is accepted too: the documented example shows one, and
    treating it as a single pointer costs nothing.

    Returns:
        One dict per change pointer, in delivery order.
    """
    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise NotificationError(f"body is not valid JSON: {exc}") from exc

    envelopes = payload if isinstance(payload, list) else [payload]
    pointers = []
    for envelope in envelopes:
        if not isinstance(envelope, dict):
            raise NotificationError("entry is not a JSON object")
        pointer = envelope.get("data", envelope)
        if not isinstance(pointer, dict):
            raise NotificationError("entry's 'data' is not a JSON object")
        pointers.append(pointer)

    if not pointers:
        raise NotificationError("body carried no change pointers")
    return pointers
