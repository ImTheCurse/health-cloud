"""SQLModel table definitions.

Every model must be imported here so ``SQLModel.metadata`` sees it before
``create_all()`` runs.

- ``users``                       healthUserId, encrypted tokens, consent times
- ``raw_notifications``           append-only audit log of webhook deliveries
- ``observation_time_intervals``  measurements accumulated over a window
- ``observation_sample_times``    measurements taken at an instant
- ``session_time_intervals``      windows bundling metrics and sub-intervals
- ``session_segments``            a session's sub-intervals: stages, laps, events
- ``unknown_data_points``         anything whose time structure is unrecognised

The three measurement tables mirror Google's three time structures rather than
its data type names; see ``server.models.datapoint``.
"""

from server.models.datapoint import (
    DataPointBase,
    ObservationSampleTime,
    ObservationTimeInterval,
    SessionSegment,
    SessionTimeInterval,
    UnknownDataPoint,
)
from server.models.notification import RawNotification
from server.models.user import User

__all__ = [
    "DataPointBase",
    "ObservationSampleTime",
    "ObservationTimeInterval",
    "RawNotification",
    "SessionSegment",
    "SessionTimeInterval",
    "UnknownDataPoint",
    "User",
]
