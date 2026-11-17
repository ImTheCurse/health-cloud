import Tooltip from "@mui/material/Tooltip";

import { formatMinutes, formatTime } from "../format.js";

const HOURS = [0, 3, 6, 9, 12, 15, 18, 21, 24];

/**
 * One day, midnight to midnight, as one lane per category with a block for
 * each stretch in it: zones, activity levels, idle periods, exercise.
 *
 * - `lanes`: `[{ id, label, color, spans: [{ from, to, start, end, minutes, detail? }] }]`,
 *   `from` and `to` in minutes since midnight.
 */
export default function Lanes({ lanes, label }) {
  return (
    <div className="lanes" role="img" aria-label={label}>
      {lanes.map((lane) => (
        <div key={lane.id} className="lane">
          <span className="lane-label">
            <span className="swatch block" style={{ "--swatch": lane.color }} aria-hidden="true" />
            {lane.label}
            <span className="lane-total">{formatMinutes(lane.spans.reduce((sum, s) => sum + s.minutes, 0))}</span>
          </span>
          <div className="lane-track">
            {lane.spans.map((span) => (
              <Tooltip
                key={span.from}
                arrow
                placement="top"
                disableInteractive
                title={
                  <span className="tip">
                    <strong>
                      {lane.label}, {formatTime(span.start)}–{formatTime(span.end)}
                    </strong>
                    <span className="tip-row">{span.detail ?? formatMinutes(span.minutes)}</span>
                  </span>
                }
              >
                <span
                  className="lane-span"
                  tabIndex={0}
                  style={{
                    left: `${(span.from / 1440) * 100}%`,
                    width: `max(4px, ${((span.to - span.from) / 1440) * 100}%)`,
                    background: lane.color,
                  }}
                />
              </Tooltip>
            ))}
          </div>
        </div>
      ))}
      <div className="lane">
        <span className="lane-label" />
        <div className="lane-axis">
          {HOURS.map((hour) => (
            <span key={hour} style={{ left: `${(hour / 24) * 100}%` }}>
              {String(hour % 24).padStart(2, "0")}:00
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
