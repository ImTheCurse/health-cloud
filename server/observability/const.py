"""Constants for request logging."""

from enum import StrEnum
from typing import Final

#: Echoed on every response so a line in the log can be traced to a request
#: someone is holding in front of them. Never read from the inbound request:
#: this endpoint is internet-facing, and accepting a caller's id would let
#: them collide or forge correlation.
REQUEST_ID_HEADER: Final = "X-Request-ID"

#: Where the request's record hangs off request.state.
STATE_ATTRIBUTE: Final = "log_record"

#: Bytes of SHA-256 kept when identifying a user in a log line. Six hex
#: characters is plenty to follow one user through a day of logs, and
#: identifies nobody if the log leaks.
LOG_ID_BYTES: Final = 3

#: Where the decorator stashes a route's policy.
POLICY_ATTRIBUTE: Final = "_log_policy"


class LogPolicy(StrEnum):
    """How much of a request is worth saying.

    Not sampling -- nothing is discarded. The policy only chooses a level, so a
    request logged at DEBUG is still there for anyone who lowers the threshold.
    """

    #: Log every request in full. The default, so going quiet is something a
    #: route opts into visibly rather than something that happens by omission.
    ALWAYS = "always"

    #: Log in full only when the request had something to say -- an error, an
    #: exception, or a domain event. Routine successes drop to DEBUG.
    QUIET = "quiet"


#: Fields that must never reach a log, whatever happens. Bodies carry health
#: data; the rest are credentials.
#:
#: Documentation only: nothing reads this. The guarantee is enforced by the
#: middleware logging a fixed set of fields rather than by filtering, and
#: checked by the leakage tests. Kept as the statement of intent a future
#: header-logging change would need to honour.
NEVER_LOGGED: Final = (
    "authorization",
    "cookie",
    "set-cookie",
    "google-health-api-signature",
)
