"""Errors raised by the notification queue."""


class QueueError(RuntimeError):
    """Base for anything that goes wrong talking to the broker."""


class PublishError(QueueError):
    """A message was not confirmed as persisted.

    Raised when the broker refused the message, did not answer in time, or the
    publisher is not connected. The receiver turns this into a 503: Google
    retries for 7 days, so refusing to acknowledge is how the delivery survives.
    """


class DrainAborted(QueueError):
    """Stop draining now and leave everything unacknowledged.

    Raised by a handler when the *next* message would fail for the same reason
    this one did -- the case that matters being an expired refresh token, where
    nothing in the queue can be processed until the user re-consents.

    Continuing would be actively destructive. Every remaining message would fail,
    each failure spends one of its ``max_deliver`` attempts, and a queue of a
    hundred notifications would be burned through in minutes and then dropped for
    good. Stopping costs one attempt on one message and preserves the rest.
    """
