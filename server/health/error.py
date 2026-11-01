"""Errors raised while reading measurements from the Health API."""


class HealthApiError(RuntimeError):
    """Base for anything that goes wrong talking to the data API."""


class FetchError(HealthApiError):
    """Google refused a read, or answered with something unreadable.

    Retryable in principle: the message it belongs to stays unacknowledged, so
    the work returns on the next run rather than being lost.
    """


class TokenExpiredError(HealthApiError):
    """The refresh token is dead and only the user can fix it.

    Its own type because it is not a transient failure and must not be retried
    into a rate limit -- every subsequent call will fail the same way until the
    user re-consents. It is also the first of the three signals the 7-day expiry
    mitigation watches for, so the push alert keys off exactly this.
    """


class UnsupportedDataTypeError(HealthApiError):
    """This data type's measurements cannot be read with ``list``.

    Permanent, and not the user's fault or ours: Google exposes some types only
    through ``rollup``/``dailyRollup``, and some only for writing. Retrying cannot
    change that, so the caller acknowledges the message with a warning rather than
    letting it cycle until ``max_deliver``.

    Acknowledging does mean the notification is not acted on. For the rollup-only
    types that is a real gap in collection -- see ``LIST_UNSUPPORTED``.
    """
