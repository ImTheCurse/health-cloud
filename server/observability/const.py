"""Constants for request logging."""

#: Echoed on every response so a line in the log can be traced to a request
#: someone is holding in front of them. Never read from the inbound request:
#: this endpoint is internet-facing, and accepting a caller's id would let
#: them collide or forge correlation.
REQUEST_ID_HEADER = "X-Request-ID"

#: Where the request's record hangs off request.state.
STATE_ATTRIBUTE = "log_record"

#: Bytes of SHA-256 kept when identifying a user in a log line. Six hex
#: characters is plenty to follow one user through a day of logs, and
#: identifies nobody if the log leaks.
LOG_ID_BYTES = 3

#: Log every request in full. The default, so that going quiet is something a
#: route opts into visibly rather than something that happens by omission.
ALWAYS = "always"

#: Log in full only when the request had something to say -- an error, an
#: exception, or a domain event. Routine successes drop to DEBUG.
QUIET = "quiet"

#: Where the decorator stashes a route's policy.
POLICY_ATTRIBUTE = "_log_policy"

#: Fields that must never reach a log, whatever happens. Bodies carry health
#: data; the rest are credentials.
NEVER_LOGGED = ("authorization", "cookie", "set-cookie", "google-health-api-signature")
