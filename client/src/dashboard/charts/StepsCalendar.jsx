import { ResponsiveCalendar } from "@nivo/calendar";

import { addDays } from "../dates.js";
import { formatLongDay, formatNumber } from "../format.js";
import { EMPTY, nivoTheme, SEQUENTIAL, SURFACE } from "../theme.js";

/** One square per day, darker for more: weekly patterns over a season. */
export default function StepsCalendar({ rows, start, end, onDay }) {
  const data = rows.filter((row) => row.value > 0).map((row) => ({ day: row.day, value: row.value }));
  return (
    <ResponsiveCalendar
      data={data}
      from={start}
      to={addDays(end, -1)}
      theme={nivoTheme}
      margin={{ top: 20, right: 8, bottom: 4, left: 24 }}
      colors={SEQUENTIAL.slice(1)}
      emptyColor={EMPTY}
      monthBorderColor={SURFACE}
      monthBorderWidth={2}
      dayBorderColor={SURFACE}
      dayBorderWidth={2}
      monthLegendOffset={8}
      tooltip={({ day, value, date }) => (
        <div className="tip">
          <strong>{formatLongDay(date ?? new Date(day))}</strong>
          <div className="tip-row">{formatNumber(Number(value))} steps</div>
        </div>
      )}
      onClick={(datum) => onDay?.(datum.day)}
      role="img"
    />
  );
}
