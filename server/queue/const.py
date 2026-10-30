"""Constants for the notification queue."""

from typing import Final

#: The JetStream stream every change pointer lands in. File-backed, so a broker
#: restart does not discard work that has not been fetched yet.
STREAM_NAME: Final = "health"

#: Subjects are `health.notifications.<dataType>`. One subject per data type,
#: rather than a single firehose, so a later consumer can subscribe to just the
#: types it cares about without filtering client-side.
SUBJECT_PREFIX: Final = "health.notifications"

#: A data type is absent or unrecognisable often enough to plan for -- Google
#: could add one tomorrow -- and a message with no subject is unroutable.
UNKNOWN_DATA_TYPE: Final = "unknown"

#: How long to wait for the broker's PubAck. Short on purpose: the caller is
#: inside Google's acknowledgement deadline, and a slow broker should surface as
#: a 503 that Google retries rather than as a request that hangs.
PUBLISH_TIMEOUT_SECONDS: Final = 5.0

#: How long to wait for the initial connection and stream setup at startup.
CONNECT_TIMEOUT_SECONDS: Final = 10.0


#: The durable consumer the fetcher flow pulls through. Durable, so its position
#: survives a restart: an ephemeral consumer would start again from whatever the
#: stream's policy says and could re-deliver or skip work.
CONSUMER_NAME: Final = "fetcher"

#: Messages pulled per request. A run keeps pulling until the stream is empty, so
#: this bounds one round trip rather than one run.
FETCH_BATCH_SIZE: Final = 50

#: How long the broker waits for an ack before assuming the consumer died and
#: redelivering. Comfortably longer than a token refresh plus a paginated fetch
#: plus a commit, because a redelivery *while the first attempt is still working*
#: is the one failure mode that turns at-least-once into duplicated effort.
ACK_WAIT_SECONDS: Final = 60

#: How many times one message may be redelivered before the broker stops. A
#: payload our parser cannot handle should fail five times and then stop, not
#: occupy the consumer forever.
MAX_DELIVER: Final = 5

#: How long to wait for a batch before concluding the stream is empty. Short: an
#: empty pull is the normal way a run finds out it is done.
PULL_TIMEOUT_SECONDS: Final = 5.0
