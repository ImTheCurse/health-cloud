"""Constants for the stored heart-rate summaries."""

import datetime as dt
from typing import Final

#: The samples an hour's figures come from.
HEART_RATE: Final = "heart-rate"

#: Google's own time-in-zone windows, which an hour's zone minutes come from.
TIME_IN_ZONE: Final = "time-in-heart-rate-zone"

#: The types whose writes make an hour's summary stale.
ROLLED_UP_TYPES: Final = frozenset({HEART_RATE, TIME_IN_ZONE})

#: The payload field naming a time-in-zone window's zone.
ZONE_KEY: Final = "heartRateZoneType"

#: How much is rebuilt per commit: a day of hours.
REBUILD_CHUNK: Final = dt.timedelta(days=1)

#: The furthest a local clock sits from UTC. A window known only in UTC is
#: widened by this much to be sure of covering every local hour it touches.
MAX_UTC_OFFSET: Final = dt.timedelta(hours=14)
