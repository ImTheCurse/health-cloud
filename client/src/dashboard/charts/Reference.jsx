// Pieces drawn on top of every chart: the dashed average, maximum and minimum
// lines, and labels with a background so they stay readable over the data.

import { formatNumber } from "../format.js";
import { REFERENCE_KEYS } from "./stats.js";

const LABEL_GAP = 15;

/** Dashed horizontal lines for the switched-on statistics, labelled at the right. */
export function ReferenceLines({ stats, hidden, yScale, width, height, format }) {
  if (!stats) return null;
  const lines = REFERENCE_KEYS.filter((key) => !hidden?.has(key.id))
    .map((key) => ({ ...key, value: stats[key.id], y: yScale(stats[key.id]) }))
    .filter((line) => line.y >= 0 && line.y <= height)
    .sort((a, b) => a.y - b.y);

  // Push labels apart so close lines stay legible.
  let previous = -Infinity;
  for (const line of lines) {
    line.labelY = Math.max(line.y, previous + LABEL_GAP);
    previous = line.labelY;
  }

  return (
    <g pointerEvents="none">
      {lines.map((line) => (
        <g key={line.id}>
          <line
            x1={0}
            x2={width}
            y1={line.y}
            y2={line.y}
            stroke={line.color}
            strokeWidth={1.5}
            strokeDasharray={line.id === "avg" ? "6 4" : "2 3"}
          />
          <Tag x={width - 2} y={line.labelY} anchor="end" color={line.color}>
            {`${line.id} ${format ? format(line.value) : formatNumber(line.value, 1)}`}
          </Tag>
        </g>
      ))}
    </g>
  );
}

/** A small text label on a white plate, so it reads over lines and bars. */
export function Tag({ x, y, anchor = "start", color, children }) {
  const text = String(children);
  const width = text.length * 6.4 + 8;
  const left = anchor === "end" ? x - width : anchor === "middle" ? x - width / 2 : x;
  return (
    <g pointerEvents="none">
      <rect x={left} y={y - 8} width={width} height={16} rx={2} fill="#ffffff" fillOpacity={0.92} />
      <text
        x={left + 4}
        y={y + 4}
        fontSize={11}
        fontWeight={600}
        fill={color}
        style={{ fontFamily: '"IBM Plex Mono", ui-monospace, monospace' }}
      >
        {text}
      </text>
    </g>
  );
}

/**
 * A ring around an extreme point with its value beside it: above the point,
 * or below for a minimum, flipped when that would leave the plot.
 */
export function ExtremeMark({ x, y, color, label, below, height = Infinity }) {
  let labelY = below ? y + 18 : y - 18;
  if (labelY > height - 10) labelY = y - 18;
  if (labelY < 8) labelY = y + 18;
  return (
    <g pointerEvents="none">
      <circle cx={x} cy={y} r={6} fill="#ffffff" stroke={color} strokeWidth={2} />
      <circle cx={x} cy={y} r={2.5} fill={color} />
      <Tag x={x} y={labelY} anchor="middle" color={color}>
        {label}
      </Tag>
    </g>
  );
}
