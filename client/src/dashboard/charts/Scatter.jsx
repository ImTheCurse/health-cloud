import { ResponsiveScatterPlot } from "@nivo/scatterplot";
import { useMemo, useState } from "react";

import { usePreview } from "../chartMode.js";
import { HOVER, INK, nivoTheme, REFERENCE } from "../theme.js";
import { ExtremeMark, ReferenceLines } from "./Reference.jsx";
import { summarize } from "./stats.js";

const MARGIN = { top: 26, right: 16, bottom: 42, left: 52 };

/**
 * Dots on two axes, with an optional line through them. With `format`, also
 * the dashed average, max and min of y and the extreme dots ringed.
 *
 * - `points`: `[{ x, y, color?, ... }]`; a point's own colour wins over `color`.
 * - `line`: `[{ x, y }]` drawn in ink above the dots, such as a rolling mean.
 * - `stems`: a thin line from zero up to each dot, making a dot plot of counts.
 */
export default function Scatter({
  points,
  line,
  color,
  hidden,
  format,
  xScale,
  yScale,
  axisBottom,
  axisLeft,
  tooltip,
  onPoint,
  stems = false,
}) {
  const [hovered, setHovered] = useState(null);
  const data = useMemo(() => [{ id: "points", data: points }], [points]);
  const preview = usePreview();
  const stats = useMemo(
    () => (format && !preview ? summarize(points.map((p) => p.y)) : null),
    [format, preview, points],
  );

  const layers = useMemo(
    () => [
      "grid",
      "axes",
      Halo(hovered),
      ...(stems ? [Stems(color)] : []),
      Dots(color),
      ...(line?.length > 1 ? [TrendLine(line)] : []),
      ...(stats ? [Overlay(stats, points, hidden, format)] : []),
      "mesh",
    ],
    [hovered, color, line, stats, points, hidden, format, stems],
  );

  return (
    <ResponsiveScatterPlot
      data={data}
      theme={nivoTheme}
      margin={MARGIN}
      xScale={xScale}
      yScale={yScale}
      nodeSize={12}
      axisBottom={{ tickSize: 4, tickPadding: 4, tickValues: 5, ...axisBottom }}
      axisLeft={{ tickSize: 0, tickPadding: 6, tickValues: 4, ...axisLeft }}
      gridXValues={5}
      gridYValues={4}
      useMesh
      layers={layers}
      onMouseEnter={(node) => setHovered(node.id)}
      onMouseLeave={() => setHovered(null)}
      tooltip={({ node }) => tooltip(node.data)}
      onClick={(node) => onPoint?.(node.data)}
      animate={false}
      role="img"
    />
  );
}

/** A soft disc behind the hovered dot. */
function Halo(hoveredId) {
  return function HaloLayer({ nodes }) {
    const node = nodes.find((candidate) => candidate.id === hoveredId);
    if (!node) return null;
    return <circle cx={node.x} cy={node.y} r={16} fill={HOVER} pointerEvents="none" />;
  };
}

/** A thin line from zero up to each dot. */
function Stems(fallback) {
  return function StemLayer({ nodes, yScale }) {
    const base = yScale(0);
    return (
      <g pointerEvents="none">
        {nodes.map((node) => (
          <line
            key={node.id}
            x1={node.x}
            x2={node.x}
            y1={base}
            y2={node.y}
            stroke={node.data.color ?? fallback}
            strokeWidth={2}
            strokeOpacity={0.55}
          />
        ))}
      </g>
    );
  };
}

function Dots(fallback) {
  return function DotLayer({ nodes }) {
    return (
      <g>
        {nodes.map((node) => (
          <circle
            key={node.id}
            cx={node.x}
            cy={node.y}
            r={5.5}
            fill={node.data.color ?? fallback}
            stroke="#ffffff"
            strokeWidth={1.5}
          />
        ))}
      </g>
    );
  };
}

function TrendLine(points) {
  return function Trend({ xScale, yScale }) {
    const d = points.map((p, i) => `${i ? "L" : "M"}${xScale(p.x)},${yScale(p.y)}`).join("");
    return <path d={d} fill="none" stroke={INK} strokeWidth={2} strokeOpacity={0.75} pointerEvents="none" />;
  };
}

function Overlay(stats, points, hidden, format) {
  const max = points.find((p) => p.y === stats.max);
  const min = points.find((p) => p.y === stats.min);
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
        {max && !hidden?.has("max") && (
          <ExtremeMark height={innerHeight} x={xScale(max.x)} y={yScale(max.y)} color={REFERENCE.max} label={format(max.y)} />
        )}
        {min && min !== max && !hidden?.has("min") && (
          <ExtremeMark height={innerHeight} x={xScale(min.x)} y={yScale(min.y)} color={REFERENCE.min} label={format(min.y)} below />
        )}
      </g>
    );
  };
}
