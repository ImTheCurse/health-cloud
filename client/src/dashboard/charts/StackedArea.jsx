import { ResponsiveLine } from "@nivo/line";
import { useMemo } from "react";

import { formatDay, formatDayTime } from "../format.js";
import { HOVER, nivoTheme } from "../theme.js";
import { timeAxis } from "./axis.js";

const MARGIN = { top: 16, right: 16, bottom: 30, left: 52 };

/**
 * Several series stacked as filled areas, so the parts and their total read at
 * once: the hours of a day split by activity level.
 *
 * - `series`: `[{ id, label, color, points: [{ x, y }] }]`, stacked bottom to top.
 * - `hidden`: series ids switched off in the legend.
 * - `format(value)`: a value as text, for the axis and the tooltip.
 */
export default function StackedArea({ series, hidden, from, to, format, daily = false, onDay }) {
  const data = useMemo(
    () =>
      series
        .filter((line) => !hidden?.has(line.id))
        .map((line) => ({ id: line.label, color: line.color, data: line.points })),
    [series, hidden],
  );
  const axis = timeAxis(from, to);

  return (
    <ResponsiveLine
      data={data}
      theme={nivoTheme}
      margin={MARGIN}
      colors={(line) => line.color}
      xScale={{ type: "time", format: "native", precision: "minute", min: from, max: to }}
      yScale={{ type: "linear", min: 0, max: "auto", stacked: true }}
      curve="monotoneX"
      lineWidth={1.5}
      enableArea
      areaOpacity={0.8}
      enablePoints={false}
      enableGridX={false}
      gridYValues={4}
      axisLeft={{ tickSize: 0, tickPadding: 6, tickValues: 4, format }}
      axisBottom={{ tickSize: 4, tickPadding: 4, tickValues: axis.tickValues, format: axis.format }}
      enableSlices="x"
      layers={["grid", HoverColumn, "axes", "areas", "lines", "slices", "crosshair"]}
      onClick={(datum) => {
        const x = datum.points?.[0]?.data.x;
        if (onDay && x) onDay(x);
      }}
      sliceTooltip={({ slice }) => {
        const x = slice.points[0].data.x;
        const total = slice.points.reduce((sum, point) => sum + (point.data.y ?? 0), 0);
        return (
          <div className="tip">
            <strong>{daily ? formatDay(x) : formatDayTime(x)}</strong>
            {[...slice.points].reverse().map((point) => (
              <div key={point.id} className="tip-row">
                <span className="swatch block" style={{ "--swatch": point.seriesColor }} />
                {point.seriesId}: <b>{format(point.data.y)}</b>
              </div>
            ))}
            <div className="tip-row muted">Total {format(total)}</div>
          </div>
        );
      }}
      animate={false}
      role="img"
    />
  );
}

/** A soft column behind the hovered time. */
function HoverColumn({ currentSlice, innerHeight }) {
  if (!currentSlice) return null;
  const width = Math.max(currentSlice.width, 10);
  return (
    <rect
      x={currentSlice.x - width / 2}
      y={0}
      width={width}
      height={innerHeight}
      fill={HOVER}
      pointerEvents="none"
    />
  );
}
