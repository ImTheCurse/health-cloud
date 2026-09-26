"""Constants for the notification queue."""

#: The JetStream stream every change pointer lands in. File-backed, so a broker
#: restart does not discard work that has not been fetched yet.
STREAM_NAME = "health"

#: Subjects are `health.notifications.<dataType>`. One subject per data type,
#: rather than a single firehose, so a later consumer can subscribe to just the
#: types it cares about without filtering client-side.
SUBJECT_PREFIX = "health.notifications"

#: A data type is absent or unrecognisable often enough to plan for -- Google
#: could add one tomorrow -- and a message with no subject is unroutable.
UNKNOWN_DATA_TYPE = "unknown"

#: How long to wait for the broker's PubAck. Short on purpose: the caller is
#: inside Google's acknowledgement deadline, and a slow broker should surface as
#: a 503 that Google retries rather than as a request that hangs.
PUBLISH_TIMEOUT_SECONDS = 5.0

#: How long to wait for the initial connection and stream setup at startup.
CONNECT_TIMEOUT_SECONDS = 10.0

