"""Errors raised by the notification queue."""


class QueueError(RuntimeError):
    """Base for anything that goes wrong talking to the broker."""


class PublishError(QueueError):
    """A message was not confirmed as persisted.

    Raised when the broker refused the message, did not answer in time, or the
    publisher is not connected. The receiver turns this into a 503: Google
    retries for 7 days, so refusing to acknowledge is how the delivery survives.
    """
