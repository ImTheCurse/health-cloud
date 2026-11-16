import { ResponsiveBar, ResponsiveBarCanvas } from "@nivo/bar";
import { useMemo, useState } from "react";

import { formatDay, formatDayTime, formatNumber } from "../format.js";
import { HOVER, nivoTheme, REFERENCE } from "../theme.js";
import { barLabel, barTicks } from "./axis.js";
import { ReferenceLines, Tag } from "./Reference.jsx";
import { summarize } from "./stats.js";

const MARGIN = { top: 26, right: 16, bottom: 30, left: 52 };

// Past this many bars SVG gets slow to hover; canvas draws them instead, without
// the overlays.
const CANVAS_FROM = 400;

/**
 * Bars over time, single or stacked, with the dashed average, max and min of
 * the bar totals, the extreme bars labelled, and a shaded column on hover.
 *
 * - `keys`: `[{ key, label, color }]`, stacked bottom to top.
 * - `hidden`: legend ids switched off: keys, and "avg", "max", "min".
 * - `spacers`: keys drawn invisible, such as the lead-in of a floating bar.
 * - `colorFor(bar)`: overrides the colour per bar, such as by sign.
 * - `layers`: extra SVG layers drawn above the bars.
 */
export default function Bars({
  rows,
  keys,
  hidden,
  spacers = [],
  digits = 0,
  unit = "",
  format,
  colorFor,
  layers: extraLayers = [],
  minValue = "auto",
  maxValue = "auto",
  reverse = false,
  yFormat,
  yTicks = 4,
  daily,
  references = true,
  onDay,
}) {
  const [hovered, setHovered] = useState(null);
  const shown = useMemo(() => keys.filter((k) => !hidden?.has(k.key)), [keys, hidden]);
  const colors = useMemo(() => Object.fromEntries(keys.map((k) => [k.key, k.color])), [keys]);
  const labels = useMemo(() => Object.fromEntries(keys.map((k) => [k.key, k.label])), [keys]);
  const rowByKey = useMemo(() => new Map(rows.map((row) => [row.key, row])), [rows]);
  const isDaily = daily ?? rows.every((row) => row.key.length === 10 || row.key.endsWith("T00:00"));

  const formatValue = format ?? ((value) => `${formatNumber(value, digits)}${unit}`);
  const formatShort = (value) => formatNumber(value, digits);

  // Statistics over the bars that have something in them: an empty hour is a
  // gap in the record, not a measured zero.
  const totals = useMemo(
    () =>
      rows.map((row) =>
        shown.filter((k) => !spacers.includes(k.key)).reduce((sum, k) => sum + (row[k.key] ?? 0), 0),
      ),
    [rows, shown, spacers],
  );
  const stats = useMemo(
    () => (references ? summarize(totals.filter((total) => total > 0)) : null),
    [references, totals],
  );

  const canvas = rows.length > CANVAS_FROM;
  const Chart = canvas ? ResponsiveBarCanvas : ResponsiveBar;
  const padding = rows.length > 60 ? 0.08 : 0.25;

  const layers = useMemo(() => {
    if (canvas) return undefined;
    const overlay = stats ? [Overlay(stats, totals, rows, hidden, formatShort, unit, reverse)] : [];
    return ["grid", HoverColumn(hovered), "axes", "bars", ...extraLayers, ...overlay];
    // formatShort only reads `digits`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canvas, stats, totals, rows, hidden, digits, unit, reverse, hovered, extraLayers]);

  return (
    <Chart
      data={rows}
      keys={shown.map((k) => k.key)}
      indexBy="key"
      theme={nivoTheme}
      margin={MARGIN}
      padding={padding}
      innerPadding={shown.length > 1 && rows.length <= 60 ? 1 : 0}
      groupMode="stacked"
      valueScale={{ type: "linear", min: minValue, max: maxValue, reverse }}
      colors={(bar) => {
        if (spacers.includes(bar.id)) return "transparent";
        return colorFor ? colorFor(bar) : colors[bar.id];
      }}
      borderRadius={rows.length <= 60 ? 2 : 0}
      enableLabel={false}
      enableGridY
      gridYValues={yTicks}
      axisLeft={{ tickSize: 0, tickPadding: 6, tickValues: yTicks, format: yFormat }}
      axisBottom={{
        tickSize: 4,
        tickPadding: 4,
        tickValues: barTicks(rows),
        format: (key) => barLabel(key, rows),
      }}
      layers={layers}
      onMouseEnter={(bar) => setHovered(bar.indexValue)}
      onMouseLeave={() => setHovered(null)}
      tooltip={({ id, value, indexValue }) => {
        if (spacers.includes(id)) return null;
        const row = rowByKey.get(indexValue);
        if (!row) return null;
        const parts = shown.filter((k) => !spacers.includes(k.key) && row[k.key]);
        return (
          <div className="tip">
            <strong>{isDaily ? formatDay(row.x) : formatDayTime(row.x)}</strong>
            {parts.length > 1 ? (
              parts.map((k) => (
                <div key={k.key} className={k.key === id ? "tip-row current" : "tip-row"}>
                  <span className="swatch block" style={{ "--swatch": colors[k.key] }} />
                  {labels[k.key]}: <b>{formatValue(row[k.key], row)}</b>
                </div>
              ))
            ) : (
              <div className="tip-row">
                <span className="swatch block" style={{ "--swatch": colors[id] }} />
                <b>{formatValue(value, row)}</b>
              </div>
            )}
          </div>
        );
      }}
      onClick={(bar) => {
        const row = rowByKey.get(bar.indexValue);
        if (onDay && row) onDay(row.day);
      }}
      animate={false}
      role="img"
    />
  );
}

/** A soft column behind the hovered bar. */
function HoverColumn(hoveredKey) {
  return function Hover({ bars, innerHeight }) {
    if (hoveredKey === null) return null;
    const bar = bars.find((candidate) => candidate.data.indexValue === hoveredKey);
    if (!bar) return null;
    const width = Math.max(bar.width + 6, 10);
    return (
      <rect
        x={bar.x + bar.width / 2 - width / 2}
        y={0}
        width={width}
        height={innerHeight}
        fill={HOVER}
        pointerEvents="none"
      />
    );
  };
}

/** Reference lines over the bars, and the tallest and shortest bar labelled. */
function Overlay(stats, totals, rows, hidden, format, unit, reverse) {
  const maxIndex = totals.indexOf(stats.max);
  const minIndex = totals.findIndex((total) => total === stats.min && total > 0);
  return function BarOverlay({ bars, yScale, innerWidth, innerHeight }) {
    const centre = (index) => {
      const bar = bars.find((candidate) => candidate.data.indexValue === rows[index]?.key);
      return bar ? bar.x + bar.width / 2 : null;
    };
    const mark = (index, color, value) => {
      const x = centre(index);
      if (x === null) return null;
      const y = yScale(value);
      return (
        <Tag x={x} y={reverse ? y + 12 : y - 12} anchor="middle" color={color}>
          {`${format(value)}${unit}`}
        </Tag>
      );
    };
    return (
      <g>
        <ReferenceLines
          stats={stats}
          hidden={hidden}
          yScale={yScale}
          width={innerWidth}
          height={innerHeight}
          format={format}
        />
        {!hidden?.has("max") && mark(maxIndex, REFERENCE.max, stats.max)}
        {!hidden?.has("min") && minIndex !== maxIndex && mark(minIndex, REFERENCE.min, stats.min)}
      </g>
    );
  };
}
