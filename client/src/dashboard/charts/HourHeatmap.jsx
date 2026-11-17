import { ResponsiveHeatMap } from "@nivo/heatmap";
import { useMemo } from "react";

import { parseIsoDate } from "../dates.js";
import { formatLongDay } from "../format.js";
import { EMPTY, nivoTheme, sequentialColor } from "../theme.js";

/**
 * Hour of day across, one row per day: the daily rhythm at a glance.
 * `rows` come from `hourByDay`; colour is one hue, darker for more.
 */
export default function HourHeatmap({ rows, format, onDay }) {
  const [min, max] = useMemo(() => {
    const values = rows.flatMap((row) => row.data.map((cell) => cell.y)).filter((y) => y !== null);
    return values.length ? [Math.min(...values), Math.max(...values)] : [0, 1];
  }, [rows]);

  return (
    <ResponsiveHeatMap
      data={rows}
      theme={nivoTheme}
      margin={{ top: 22, right: 8, bottom: 4, left: 84 }}
      xInnerPadding={0.06}
      yInnerPadding={0.08}
      borderRadius={1}
      colors={(cell) => sequentialColor(cell.value, min, max)}
      emptyColor={EMPTY}
      enableLabels={false}
      axisTop={{
        tickSize: 0,
        tickPadding: 4,
        format: (hour) => (Number(hour) % 3 === 0 ? hour : ""),
      }}
      axisLeft={{
        tickSize: 0,
        tickPadding: 6,
        format: (day) => formatLongDay(parseIsoDate(day)),
      }}
      hoverTarget="cell"
      inactiveOpacity={1}
      tooltip={({ cell }) => (
        <div className="tip">
          <strong>
            {formatLongDay(parseIsoDate(cell.serieId))}, {cell.data.x}:00
          </strong>
          <div className="tip-row">{cell.value === null ? "No data" : format(cell.value)}</div>
        </div>
      )}
      onClick={(cell) => onDay?.(cell.serieId)}
      animate={false}
      role="img"
    />
  );
}
