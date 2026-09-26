"""Helpers for the notification queue."""

from server.queue.const import SUBJECT_PREFIX, UNKNOWN_DATA_TYPE


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
