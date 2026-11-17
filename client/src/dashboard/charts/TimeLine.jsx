import { ResponsiveLine } from "@nivo/line";
import { useMemo } from "react";

import { usePreview } from "../chartMode.js";
import { addDays, isoDate, parseIsoDate } from "../dates.js";
import { formatDay, formatDayTime, formatNumber } from "../format.js";
import { HOVER, INK_SOFT, nivoTheme, PERSONAL_BAND, PERSONAL_TONE, REFERENCE, RULE } from "../theme.js";
import { timeAxis } from "./axis.js";
import { ExtremeMark, ReferenceLines } from "./Reference.jsx";
import { summarize } from "./stats.js";

const MARGIN = { top: 26, right: 16, bottom: 30, left: 48 };

/**
 * Lines over time, with the dashed average, max and min of the first line, its
 * extreme points ringed, and a shaded column under the hovered time.
 *
 * - `series`: `[{ id, label, color, points: [{ x: Date, y }] }]`; nulls break a line.
 * - `hidden`: ids switched off in the legend, series and reference lines alike.
 * - `bands`: `[{ from, to, label, color }]` in value units, such as heart-rate zones.
 * - `stepColors`: per-level colours; draws a step line coloured by level, as sleep stages.
 * - `personal`: `{ ranges: Map<iso, { low, high }>, notes: { above, below } }`, your
 *   usual range per day; drawn as a band, with each point outside it ringed and
 *   its meaning in the tooltip. Switched off with the legend id "personal".
 * - `onDay(iso)`: called with the date clicked.
 */
export default function TimeLine({
  series,
  hidden,
  bands,
  stepColors,
  from,
  to,
  digits = 0,
  unit = "",
  curve = "monotoneX",
  yMin = "auto",
  yMax = "auto",
  yFormat,
  yTicks,
  daily = false,
  references = true,
  tipExtra,
  personal,
  onDay,
}) {
  const visible = useMemo(() => series.filter((line) => !hidden?.has(line.id)), [series, hidden]);
  const data = useMemo(
    () => visible.map((line) => ({ id: line.label, color: line.color, data: line.points })),
    [visible],
  );

  const formatValue = (value) =>
    value === null || value === undefined ? "–" : `${formatNumber(value, digits)}${unit}`;
  const formatShort = (value) => formatNumber(value, digits);

  const preview = usePreview();
  const primary = visible[0];
  const stats = useMemo(
    () => (references && !preview && primary ? summarize(primary.points.map((p) => p.y)) : null),
    [references, preview, primary],
  );
  const extremes = useMemo(() => {
    if (!stats || !primary) return null;
    const present = primary.points.filter((p) => p.y !== null && p.y !== undefined);
    return {
      max: present.find((p) => p.y === stats.max),
      min: present.find((p) => p.y === stats.min),
    };
  }, [stats, primary]);

  const ranges = personal && !hidden?.has("personal") ? personal.ranges : null;
  const outside = useMemo(() => {
    const found = new Map();
    if (!ranges || !primary) return found;
    for (const point of primary.points) {
      if (point.y === null || point.y === undefined) continue;
      const day = isoDate(point.x);
      const range = ranges.get(day);
      if (!range) continue;
      const side = point.y > range.high ? "above" : point.y < range.low ? "below" : null;
      if (side) found.set(day, { point, side, range, note: personal.notes[side] });
    }
    return found;
  }, [ranges, primary, personal]);

  // The band must fit on the chart even where it runs past the data.
  const [scaleMin, scaleMax] = useMemo(() => {
    if (!ranges || !primary || yMin !== "auto" || yMax !== "auto") return [yMin, yMax];
    const values = visible.flatMap((line) => line.points.map((p) => p.y)).filter((y) => typeof y === "number");
    for (const range of ranges.values()) values.push(range.low, range.high);
    if (!values.length) return [yMin, yMax];
    const low = Math.min(...values);
    const high = Math.max(...values);
    const pad = (high - low || 1) * 0.06;
    return [low - pad, high + pad];
  }, [ranges, primary, visible, yMin, yMax]);

  const pointCount = Math.max(0, ...visible.map((line) => line.points.length));
  const pointSize = pointCount <= 40 && !stepColors ? 7 : 0;

  const layers = useMemo(() => {
    const below = [HoverColumn];
    if (ranges?.size) below.push(PersonalBand(ranges));
    if (bands?.length) below.push(ReferenceBands(bands));
    const lines = stepColors ? [StepLine(stepColors)] : ["lines"];
    const above = [];
    if (stats) above.push(Overlay(stats, extremes, hidden, formatShort, unit));
    if (outside.size) above.push(PersonalMarks(outside));
    return ["grid", ...below, "axes", ...lines, "points", ...above, "slices", "crosshair"];
    // formatShort only reads `digits`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bands, stepColors, stats, extremes, hidden, primary, digits, unit, ranges, outside]);

  const axis = timeAxis(from, to);

  return (
    <ResponsiveLine
      data={data}
      theme={nivoTheme}
      margin={MARGIN}
      colors={(line) => line.color}
      xScale={{ type: "time", format: "native", precision: "minute", min: from, max: to }}
      yScale={{ type: "linear", min: scaleMin, max: scaleMax }}
      curve={curve}
      lineWidth={2.25}
      pointSize={pointSize}
      pointColor="#ffffff"
      pointBorderWidth={2}
      pointBorderColor={{ from: "seriesColor" }}
      enableGridX={false}
      gridYValues={yTicks ?? 4}
      axisLeft={{ tickSize: 0, tickPadding: 6, tickValues: yTicks ?? 4, format: yFormat }}
      axisBottom={{ tickSize: 4, tickPadding: 4, tickValues: axis.tickValues, format: axis.format }}
      enableSlices="x"
      layers={layers}
      onClick={(datum) => {
        const x = datum.points?.[0]?.data.x ?? datum.data?.x;
        if (onDay && x) onDay(isoDate(x));
      }}
      sliceTooltip={({ slice }) => {
        const x = slice.points[0].data.x;
        return (
          <div className="tip">
            <strong>{daily ? formatDay(x) : formatDayTime(x)}</strong>
            {slice.points.map((point) => (
              <div key={point.id} className="tip-row">
                <span className="swatch line" style={{ "--swatch": point.seriesColor }} />
                {slice.points.length > 1 ? `${point.seriesId}: ` : ""}
                <b>{yFormat ? yFormat(point.data.y) : formatValue(point.data.y)}</b>
              </div>
            ))}
            {tipExtra?.(x) && <div className="tip-row muted">{tipExtra(x)}</div>}
            {ranges && (
              <PersonalNote
                day={isoDate(x)}
                ranges={ranges}
                outside={outside}
                format={formatValue}
                subject={visible.length > 1 ? primary.label : null}
              />
            )}
          </div>
        );
      }}
      animate={false}
      role="img"
    />
  );
}

/** A soft column behind the hovered time, so the point under it stands out. */
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

function Overlay(stats, extremes, hidden, format, unit) {
  return function StatOverlay({ xScale, yScale, innerWidth, innerHeight }) {
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
        {extremes?.max && !hidden?.has("max") && (
          <ExtremeMark
            height={innerHeight}
            x={xScale(extremes.max.x)}
            y={yScale(extremes.max.y)}
            color={REFERENCE.max}
            label={`${format(extremes.max.y)}${unit}`}
          />
        )}
        {extremes?.min && extremes.min !== extremes.max && !hidden?.has("min") && (
          <ExtremeMark
            height={innerHeight}
            x={xScale(extremes.min.x)}
            y={yScale(extremes.min.y)}
            color={REFERENCE.min}
            label={`${format(extremes.min.y)}${unit}`}
            below
          />
        )}
      </g>
    );
  };
}

/** Each level of a step line in its own colour; grey risers between levels. */
function StepLine(colors) {
  return function Steps({ series, xScale, yScale }) {
    return (
      <g>
        {series.map((line) =>
          line.data.map((point, index) => {
            const next = line.data[index + 1];
            if (!next || point.data.y === null) return null;
            const x1 = xScale(point.data.x);
            const x2 = xScale(next.data.x);
            const y = yScale(point.data.y);
            const yNext = yScale(next.data.y);
            return (
              <g key={`${line.id}-${index}`}>
                <line x1={x2} x2={x2} y1={y} y2={yNext} stroke={RULE} strokeWidth={1} />
                <line
                  x1={x1}
                  x2={x2}
                  y1={y}
                  y2={y}
                  stroke={colors[point.data.y] ?? INK_SOFT}
                  strokeWidth={8}
                  strokeLinecap="butt"
                />
              </g>
            );
          }),
        )}
      </g>
    );
  };
}

/** Horizontal bands across the plot, clipped to it, labelled at the left. */
function ReferenceBands(bands) {
  return function References({ yScale, innerWidth, innerHeight }) {
    return (
      <g pointerEvents="none">
        {bands.map((band) => {
          const top = Math.max(0, Math.min(innerHeight, yScale(band.to)));
          const bottom = Math.max(0, Math.min(innerHeight, yScale(band.from)));
          if (bottom - top < 1) return null;
          return (
            <g key={band.label}>
              <rect x={0} y={top} width={innerWidth} height={bottom - top} fill={band.color} fillOpacity={0.1} />
              {bottom - top > 14 && (
                <text x={6} y={top + 13} fontSize={11} fontWeight={600} fill={band.color}>
                  {band.label}
                </text>
              )}
            </g>
          );
        })}
      </g>
    );
  };
}

/** Your usual range as a light green band, one step per day. */
function PersonalBand(ranges) {
  return function Band({ xScale, yScale, innerWidth, innerHeight }) {
    return (
      <g pointerEvents="none">
        {[...ranges.entries()].map(([day, range]) => {
          const centre = xScale(parseIsoDate(day));
          const width = xScale(parseIsoDate(addDays(day, 1))) - centre;
          const left = Math.max(0, centre - width / 2);
          const right = Math.min(innerWidth, centre + width / 2);
          const top = Math.max(0, yScale(range.high));
          const bottom = Math.min(innerHeight, yScale(range.low));
          if (right <= left || bottom <= top) return null;
          return (
            <rect key={day} x={left} y={top} width={right - left} height={bottom - top} fill={PERSONAL_BAND} />
          );
        })}
      </g>
    );
  };
}

/** A ring and an arrow on each point outside your range: blue good, orange watch. */
function PersonalMarks(outside) {
  return function Marks({ xScale, yScale }) {
    return (
      <g pointerEvents="none">
        {[...outside.entries()].map(([day, { point, side, note }]) => {
          const x = xScale(point.x);
          const y = yScale(point.y);
          const color = PERSONAL_TONE[note.tone];
          const arrowY = side === "above" ? y - 13 : y + 13;
          return (
            <g key={day}>
              <circle cx={x} cy={y} r={7} fill="none" stroke={color} strokeWidth={2.5} />
              <path
                d={
                  side === "above"
                    ? `M${x - 4},${arrowY + 3} L${x},${arrowY - 3} L${x + 4},${arrowY + 3}`
                    : `M${x - 4},${arrowY - 3} L${x},${arrowY + 3} L${x + 4},${arrowY - 3}`
                }
                fill="none"
                stroke={color}
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </g>
          );
        })}
      </g>
    );
  };
}

/** The personal-range line of a tooltip: inside it, or what being outside means. */
function PersonalNote({ day, ranges, outside, format, subject }) {
  const range = ranges.get(day);
  if (!range) return null;
  const span = `${format(range.low)}–${format(range.high)}`;
  const hit = outside.get(day);
  const sentence = (text) => (subject ? `${subject} ${text}` : text.charAt(0).toUpperCase() + text.slice(1));
  if (!hit) return <div className="tip-row muted">{sentence(`within your usual range (${span})`)}</div>;
  return (
    <div className={`tip-note ${hit.note.tone}`}>
      <b>
        {hit.side === "above" ? "↑ " : "↓ "}
        {sentence(`${hit.side} your usual range (${span})`)}
      </b>
      <span>{hit.note.text}</span>
    </div>
  );
}
