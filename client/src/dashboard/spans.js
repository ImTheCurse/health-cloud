// How much time the group pages show: one day, a preset number of days, or a
// custom range, always ending on the chosen day.

import { addDays, datesBetween, today } from "./dates.js";

export const SPANS = ["day", "week", "month", "3m", "custom"];

export const SPAN_LABELS = { day: "Day", week: "Week", month: "Month", "3m": "3 months", custom: "Custom" };

const PRESET_DAYS = { day: 1, week: 7, month: 30, "3m": 90 };

/** The longest custom range: past this the raw-sample routes get too slow. */
export const MAX_CUSTOM_DAYS = 90;

/** Hourly buckets are offered up to this many days; longer ranges are daily. */
export const MAX_HOURLY_DAYS = 7;

/** The day the view ends on: the chosen one, or today. */
export function endDay(state) {
  return state.day ?? today();
}

/** The first day shown, inclusive. */
export function startDay(state) {
  const end = endDay(state);
  if (state.span === "custom") return clampStart(state.from ?? end, end);
  return addDays(end, 1 - PRESET_DAYS[state.span]);
}

/** How many days the view covers. */
export function spanDays(state) {
  return datesBetween(startDay(state), addDays(endDay(state), 1)).length;
}

/** A custom start kept on or before `end` and at most MAX_CUSTOM_DAYS before it. */
export function clampStart(start, end) {
  const earliest = addDays(end, 1 - MAX_CUSTOM_DAYS);
  if (start > end) return end;
  return start < earliest ? earliest : start;
}

/** The bucket size a range actually uses: the chosen one where allowed, else daily. */
export function rangeBucket(state) {
  return spanDays(state) <= MAX_HOURLY_DAYS ? state.bucket : "1d";
}

/**
 * The view a group renders. A single day is "day" mode at the chosen day
 * resolution; anything longer is "range" mode. `end` is the day after the last
 * one shown, because the API excludes it.
 */
export function viewOf(state, group, onDay) {
  const start = startDay(state);
  const end = addDays(endDay(state), 1);
  if (state.span === "day") {
    return { mode: "day", start, end, resolution: state.res, days: 1, onDay };
  }
  const days = spanDays(state);
  return {
    mode: "range",
    start,
    end,
    resolution: group.bucketed ? rangeBucket(state) : "1d",
    days,
    onDay,
  };
}
