// Non-component helpers shared by the tabs: chart bounds,
// reading lookups and exercise colours.

import { useMemo } from "react";

import { parseIsoDate } from "../dates.js";
import { humanize } from "../format.js";
import { exerciseTypesByCount } from "../series.js";
import { OTHER, SERIES } from "../theme.js";

export function useBounds(view) {
  return useMemo(
    () => ({ from: parseIsoDate(view.start), to: parseIsoDate(view.end) }),
    [view.start, view.end],
  );
}

// Overlapping dots need more colour distance than adjacent bars, so a swarm
// gets three hues and everything else shares "other".
const SWARM_HUES = 3;

/** Colours for the exercise types present: the most frequent get the hues. */
export function useTypeColors(sessions) {
  return useMemo(() => {
    const types = exerciseTypesByCount(sessions);
    const coloured = types.slice(0, SWARM_HUES);
    const colorOf = (type) => {
      const index = coloured.indexOf(type ?? "OTHER");
      return index === -1 ? OTHER : SERIES[index];
    };
    const legend = coloured.map((type, index) => ({ label: humanize(type), color: SERIES[index] }));
    if (types.length > SWARM_HUES) legend.push({ label: "Other", color: OTHER });
    return { colorOf, legend };
  }, [sessions]);
}

/** The value of `field` in the last reading of a Readings payload. */
export function latestReading(readings, field) {
  const list = readings?.readings ?? [];
  for (let index = list.length - 1; index >= 0; index -= 1) {
    const value = list[index].values[field];
    if (value !== undefined && value !== null) return value;
  }
  return null;
}
