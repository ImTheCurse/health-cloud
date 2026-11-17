import { ResponsiveHeatMap } from "@nivo/heatmap";
import { useMemo } from "react";

import { parseIsoDate } from "../dates.js";
import { formatDay, formatLongDay } from "../format.js";
import { EMPTY, nivoTheme, sequentialColor } from "../theme.js";

// Date labels across the top, thinned to about this many.
const MAX_LABELS = 8;

/**
 * One row per category, one column per day, darker for more: which days were
 * hard, and in which category. Each row is named on the left, so colour is
 * never the only cue.
 *
 * - `rows`: `[{ id, label, data: [{ x: day, y }] }]`, top to bottom.
 * - `format(value)`: a cell's value as text, for the tooltip.
 */
export default function DayHeatmap({ rows, format, onDay }) {
  const [min, max] = useMemo(() => {
    const values = rows.flatMap((row) => row.data.map((cell) => cell.y)).filter((y) => y !== null);
    return values.length ? [0, Math.max(...values)] : [0, 1];
  }, [rows]);
  const labels = useMemo(() => new Map(rows.map((row) => [row.id, row.label])), [rows]);
  const days = rows[0]?.data.map((cell) => cell.x) ?? [];
  const step = Math.max(1, Math.ceil(days.length / MAX_LABELS));

  return (
    <ResponsiveHeatMap
      data={rows}
      theme={nivoTheme}
      margin={{ top: 22, right: 8, bottom: 4, left: 84 }}
      xInnerPadding={days.length > 31 ? 0.04 : 0.08}
      yInnerPadding={0.12}
      borderRadius={2}
      colors={(cell) => (cell.value ? sequentialColor(cell.value, min, max) : EMPTY)}
      emptyColor={EMPTY}
      enableLabels={false}
      axisTop={{
        tickSize: 0,
        tickPadding: 4,
        format: (day) => (days.indexOf(day) % step === 0 ? formatDay(parseIsoDate(day)) : ""),
      }}
      axisLeft={{ tickSize: 0, tickPadding: 6, format: (id) => labels.get(id) ?? id }}
      hoverTarget="cell"
      inactiveOpacity={1}
      tooltip={({ cell }) => (
        <div className="tip">
          <strong>
            {labels.get(cell.serieId)}, {formatLongDay(parseIsoDate(cell.data.x))}
          </strong>
          <div className="tip-row">{cell.value ? format(cell.value) : "None"}</div>
        </div>
      )}
      onClick={(cell) => onDay?.(cell.data.x)}
      animate={false}
      role="img"
    />
  );
}
