// The home page's figures: one value per day from each route, the day shown
// against the seven days before it. Pure functions only.

import { addDays, minuteKey } from "./dates.js";
import { dailyReadingValues, personalRanges } from "./series.js";

/** Days compared against: the seven complete days before the day shown. */
export const BASELINE_DAYS = 7;

/** One value per day from hourly bucket payloads, folded by `reduce`. */
function byDay(buckets, reduce) {
  const groups = new Map();
  for (const bucket of buckets ?? []) {
    const day = bucket.start.slice(0, 10);
    if (!groups.has(day)) groups.set(day, []);
    groups.get(day).push(bucket);
  }
  return new Map([...groups.entries()].map(([day, list]) => [day, reduce(list)]));
}

/** The hourly buckets of the last 24 hours, the current hour included. */
function lastDay(buckets, now) {
  const hour = new Date(now);
  hour.setMinutes(0, 0, 0);
  hour.setHours(hour.getHours() - 23);
  const pad = (n) => String(n).padStart(2, "0");
  const cutoff = `${hour.getFullYear()}-${pad(hour.getMonth() + 1)}-${pad(hour.getDate())}T${pad(hour.getHours())}:00`;
  return (buckets ?? []).filter((bucket) => minuteKey(bucket.start) >= cutoff);
}

const sumTotals = (list) => list.reduce((sum, bucket) => sum + bucket.total, 0);

const sumCategories = (list) =>
  list.reduce((sum, bucket) => sum + Object.values(bucket.totals).reduce((a, b) => a + b, 0), 0);

/** The mean of hourly means, each weighted by how many samples it holds. */
function weightedMean(list) {
  let sum = 0;
  let count = 0;
  for (const bucket of list) {
    sum += bucket.avg * bucket.count;
    count += bucket.count;
  }
  return count ? sum / count : null;
}

/**
 * How each tile reads its payload. `daily` gives a value per date; `rolling`,
 * where present, gives the last 24 hours, used in place of today.
 */
export const READERS = {
  sum: {
    daily: (payload) => byDay(payload?.buckets, sumTotals),
    rolling: (payload, now) => {
      const recent = lastDay(payload?.buckets, now);
      return recent.length ? sumTotals(recent) : null;
    },
  },
  categories: {
    daily: (payload) => byDay(payload?.buckets, sumCategories),
    rolling: (payload, now) => {
      const recent = lastDay(payload?.buckets, now);
      return recent.length ? sumCategories(recent) : null;
    },
  },
  mean: {
    daily: (payload) => byDay(payload?.buckets, weightedMean),
    rolling: (payload, now) => weightedMean(lastDay(payload?.buckets, now)),
  },
  reading: (field) => ({
    daily: (payload) => dailyReadingValues([payload], field),
  }),
  sleep: {
    daily: (payload) =>
      new Map(
        (payload?.days ?? [])
          .filter((day) => day.total_minutes_asleep > 0)
          .map((day) => [day.date, day.total_minutes_asleep]),
      ),
  },
  temperature: {
    daily: (payload) => {
      const nightly = dailyReadingValues([payload], "nightly_celsius");
      const baseline = dailyReadingValues([payload], "baseline_celsius");
      const result = new Map();
      for (const [day, value] of nightly) {
        if (baseline.has(day)) result.set(day, value - baseline.get(day));
      }
      return result;
    },
  },
};

/**
 * `history`, where given, is a second payload of the same route covering the
 * days before `payload`, read only for the personal range.
 *
 * The figure for `day` and how it compares with the seven days before:
 * `{ value, rolling, average, low, high, usual }`. `rolling` says the value is
 * the last 24 hours rather than the calendar day. `average`, `low` and `high`
 * are null when none of the seven days has a value. `usual` is the personal
 * range, `{ low, high }` from the 30 days before, or null when the payload
 * holds too little history for one.
 */
export function summarise(payload, reader, day, isToday, now = new Date(), history = null) {
  const values = reader.daily(payload);
  const rolling = Boolean(isToday && reader.rolling);
  const value = rolling ? reader.rolling(payload, now) : values.get(day) ?? null;
  const longer = history ? new Map([...reader.daily(history), ...values]) : values;
  const usual = personalRanges(longer, [day]).get(day) ?? null;

  const before = [];
  for (let back = 1; back <= BASELINE_DAYS; back += 1) {
    const past = values.get(addDays(day, -back));
    if (typeof past === "number" && !Number.isNaN(past)) before.push(past);
  }
  if (before.length === 0) return { value, rolling, usual, average: null, low: null, high: null };
  return {
    value,
    rolling,
    usual,
    average: before.reduce((a, b) => a + b, 0) / before.length,
    low: Math.min(...before),
    high: Math.max(...before),
  };
}
