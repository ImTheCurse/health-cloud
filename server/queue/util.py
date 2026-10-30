"""Helpers for the notification queue."""

import json
from typing import Any

from server.queue.const import SUBJECT_PREFIX, UNKNOWN_DATA_TYPE
from server.queue.error import QueueError


def subject_for(data_type: str | None, prefix: str = SUBJECT_PREFIX) -> str:
    """The subject a pointer for this data type belongs on.

    Example:
        >>> subject_for("sleep")
        'health.notifications.sleep'
        >>> subject_for(None)
        'health.notifications.unknown'
        >>> subject_for("steps", prefix="other")
        'other.steps'
    """
    return f"{prefix}.{data_type or UNKNOWN_DATA_TYPE}"


def decode_notification(data: bytes) -> dict[str, Any]:
    """The message body the publisher wrote, back into a dict.

    Raises:
        QueueError: the body is not the JSON object the publisher writes. A
            message we cannot read is permanent rather than transient -- no
            number of redeliveries makes it parseable -- so the caller terminates
            it rather than retrying.
    """
    try:
        payload = json.loads(data)
    except (ValueError, UnicodeDecodeError) as error:
        raise QueueError(f"message body was not JSON: {type(error).__name__}") from error

    if not isinstance(payload, dict):
        raise QueueError(f"message body was {type(payload).__name__}, not an object")
    if not isinstance(payload.get("pointer"), dict):
        raise QueueError("message body carried no change pointer")
    return payload
