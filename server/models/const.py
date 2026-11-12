"""Constants for the table definitions."""

from enum import StrEnum
from typing import Final


class TimeStructure(StrEnum):
    """Which of Google's time shapes a dataPoint carries.

    The API models time three ways, and the shape -- not the data type's name --
    is what decides which table a point belongs in. Routing on the shape means a
    data type Google adds tomorrow lands in the right table with no code change,
    which is the same reasoning that keeps ``DATA_TYPES`` a tuple and not an
    enum.

    Ours rather than Google's, so a closed set is safe: an incoming payload is
    classified into one of these or into ``UNKNOWN``, never into a member we
    have not written down.
    """

    #: ``ObservationTimeInterval`` -- accumulated over a window. Steps, distance.
    INTERVAL = "interval"
    #: ``ObservationSampleTime`` -- measured at an instant. Heart rate, weight.
    SAMPLE = "sample"
    #: ``SessionTimeInterval`` -- a window bundling metrics and sub-intervals.
    SESSION = "session"
    #: Classification failed. The payload is kept verbatim and nothing is lost.
    UNKNOWN = "unknown"


class SegmentType(StrEnum):
    """What a row in ``session_segments`` came from.

    Google has no umbrella name for a session's sub-intervals -- it names them
    per data type (``Sleep.SleepStage``, ``Sleep.OutOfBedSegment``,
    ``Exercise.SplitSummary``, ``Exercise.ExerciseEvent``) -- so the table is
    named generically and Google's vocabulary lives here, in a column that can
    be filtered on.

    A closed set because *we* assign it during extraction: an unrecognised
    nested array is left in the session's ``value`` rather than invented into a
    member.
    """

    SLEEP_STAGE = "SLEEP_STAGE"
    OUT_OF_BED_SEGMENT = "OUT_OF_BED_SEGMENT"
    SPLIT_SUMMARY = "SPLIT_SUMMARY"
    EXERCISE_EVENT = "EXERCISE_EVENT"


#: ``source_platform`` for a Fitbit device's own measurement.
FITBIT_PLATFORM: Final = "FITBIT"

#: ``source_platform`` for a total Google computed itself across every source --
#: a ``dailyRollUp`` bucket, which carries no ``dataSource`` of its own.
GOOGLE_HEALTH_PLATFORM: Final = "GOOGLE_HEALTH"


#: Written into ``data_type`` when a pointer or dataPoint names no type. Matches
#: the subject the receiver publishes such a notification to.
UNKNOWN_DATA_TYPE: Final = "unknown"
