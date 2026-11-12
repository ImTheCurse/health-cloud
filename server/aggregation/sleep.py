"""Sleep, grouped by the day the user woke up."""

import datetime as dt
from collections import defaultdict
from typing import Any

from server.aggregation.const import SLEEP_SUMMARY_FIELDS
from server.aggregation.schemas import Number, SleepDay, SleepSession, SleepStage
from server.aggregation.series import MeasurementReader
from server.aggregation.util import (
    at_path,
    local_window,
    number,
    tidy,
    tidy_or_none,
    window_minutes,
)
from server.db.measurements import Measurement
from server.models.datapoint import SessionTimeInterval

SLEEP = "sleep"


class SleepAggregator:
    """Every sleep, main and nap, on the date it ended.

    The stored ``civil_date`` is the local date a session *started*, so a night
    that began at 23:00 would land on the day before the morning it belongs to.
    A sleep is the wake-up date's, the way the Fitbit app dates it, which is why
    the read starts a day early and the grouping is done here.

    Stages come from the session's own payload, not from ``session_segments``:
    there, short awakenings are stored as stages too and overlap the real ones.
    """

    def __init__(self, reader: MeasurementReader) -> None:
        self._reader = reader

    def days(self, start: dt.date, end: dt.date) -> list[SleepDay]:
        """Sleep that ended on a date in ``[start, end)``."""
        rows = self._reader.read(
            SessionTimeInterval,
            SLEEP,
            start - dt.timedelta(days=1),
            end,
            with_value=True,
        )
        by_day: dict[dt.date, list[SleepSession]] = defaultdict(list)
        for row in rows:
            woke = _wake_date(row)
            if woke is not None and start <= woke < end:
                by_day[woke].append(_session(row))
        return [
            SleepDay(
                date=day,
                total_minutes_asleep=tidy(
                    sum(float(s.minutes_asleep or 0) for s in sessions)
                ),
                sessions=sessions,
            )
            for day, sessions in sorted(by_day.items())
        ]


def _wake_date(row: Measurement) -> dt.date | None:
    if row.local_end is not None:
        return row.local_end.date()
    return row.civil_date


def _session(row: Measurement) -> SleepSession:
    payload: Any = row.value or {}
    summary = at_path(payload, "summary") or {}
    figures = {
        name: tidy_or_none(number(summary.get(field)))
        for name, field in SLEEP_SUMMARY_FIELDS.items()
    }
    return SleepSession(
        start=row.local_start,
        end=row.local_end,
        duration_minutes=tidy(round(window_minutes(row.start_ts, row.end_ts), 2)),
        main_sleep=bool(at_path(payload, "metadata.mainSleep")),
        stage_minutes=_stage_minutes(summary.get("stagesSummary")),
        stages=_stages(payload.get("stages")),
        short_awakenings=_stages(payload.get("shortAwakenings")),
        **figures,
    )


def _stage_minutes(stages_summary: Any) -> dict[str, Number]:
    """Google's own minutes per stage, from ``stagesSummary``."""
    minutes: dict[str, Number] = {}
    if not isinstance(stages_summary, list):
        return minutes
    for entry in stages_summary:
        if not isinstance(entry, dict):
            continue
        stage, value = entry.get("type"), number(entry.get("minutes"))
        if isinstance(stage, str) and value is not None:
            minutes[stage] = tidy(value)
    return minutes


def _stages(segments: Any) -> list[SleepStage]:
    if not isinstance(segments, list):
        return []
    stages = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        start, end = local_window(segment)
        stages.append(
            SleepStage(
                stage=str(segment.get("type")),
                start=start,
                end=end,
                minutes=tidy(round(window_minutes(start, end), 2)),
            )
        )
    stages.sort(key=lambda stage: stage.start or dt.datetime.min)
    return stages
