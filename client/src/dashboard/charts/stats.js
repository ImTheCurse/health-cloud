// The statistics every chart can show as dashed lines.

import { REFERENCE } from "../theme.js";

export const REFERENCE_KEYS = [
  { id: "avg", label: "Average", color: REFERENCE.avg, shape: "dash" },
  { id: "max", label: "Max", color: REFERENCE.max, shape: "dash" },
  { id: "min", label: "Min", color: REFERENCE.min, shape: "dash" },
];

/** Lowest, highest and mean of the numbers present, or null for none. */
export function summarize(values) {
  const present = values.filter((value) => typeof value === "number" && !Number.isNaN(value));
  if (!present.length) return null;
  return {
    min: Math.min(...present),
    max: Math.max(...present),
    avg: present.reduce((sum, value) => sum + value, 0) / present.length,
  };
}
