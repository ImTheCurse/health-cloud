// Reshaping API payloads into what the charts draw. Pure functions only: no
// React, no fetching.

import {
  addDays,
  datesBetween,
  minuteKey,
  minutesOfDay,
  parseIsoDate,
  parseLocal,
  weekStart,
} from "./dates.js";

export const RESOLUTION_MINUTES = { "1m": 1, "5m": 5, "10m": 10, "30m": 30, "1h": 60, "1d": 1440 };

const pad = (n) => String(n).padStart(2, "0");

/**
 * Every bucket the range holds at `resolution`, present or not, so a gap in
 * the data stays a gap on the chart instead of closing up.
 */
export function slots(start, end, resolution) {
  const step = RESOLUTION_MINUTES[resolution];
  const result = [];
  for (const day of datesBetween(start, end)) {
    const midnight = parseIsoDate(day);
    for (let minute = 0; minute < 1440; minute += step) {
      const hours = Math.floor(minute / 60);
      result.push({
        key: `${day}T${pad(hours)}:${pad(minute % 60)}`,
        day,
        date: new Date(
          midnight.getFullYear(),
          midnight.getMonth(),
          midnight.getDate(),
          hours,
          minute % 60,
        ),
      });
    }
  }
  return result;
}

function byKey(buckets) {
  return new Map((buckets ?? []).map((bucket) => [minuteKey(bucket.start), bucket]));
}

/** A StatSeries over every slot: `{ x, day, low, mid, high }`, nulls in gaps. */
export function statRows(series, start, end, resolution) {
  const found = byKey(series?.buckets);
  return slots(start, end, resolution).map(({ key, day, date }) => {
    const bucket = found.get(key);
    return {
      key,
      day,
      x: date,
      low: bucket?.min ?? null,
      mid: bucket?.avg ?? null,
      high: bucket?.max ?? null,
    };
  });
}

/** A SumSeries over every slot, as bar rows `{ key, day, x, value }`. */
export function sumRows(series, start, end, resolution, scale = 1) {
  const found = byKey(series?.buckets);
  return slots(start, end, resolution).map(({ key, day, date }) => {
    const bucket = found.get(key);
    return { key, day, x: date, value: bucket ? bucket.total * scale : 0 };
  });
}

/** A CategorySeries over every slot, one field per category. */
export function categoryRows(series, start, end, resolution, categories) {
  const found = byKey(series?.buckets);
  return slots(start, end, resolution).map(({ key, day, date }) => {
    const totals = found.get(key)?.totals ?? {};
    const row = { key, day, x: date };
    for (const category of categories) row[category] = totals[category] ?? 0;
    return row;
  });
}

/** The categories a series actually holds, in `order`, unknown ones last. */
export function presentCategories(series, order) {
  const seen = new Set();
  for (const bucket of series?.buckets ?? []) {
    for (const [name, value] of Object.entries(bucket.totals)) if (value) seen.add(name);
  }
  const known = order.filter((name) => seen.has(name));
  const unknown = [...seen].filter((name) => !order.includes(name)).sort();
  return [...known, ...unknown];
}

/** Whether a series payload has anything to draw. */
export function hasBuckets(series) {
  return (series?.buckets ?? []).length > 0;
}

/**
 * Readings as line points, one series per field. A reading is placed on its
 * date; several on one date are averaged, which only nightly summaries do.
 */
export function readingSeries(readings, fields, scale = 1) {
  return fields.map(({ field, label }) => {
    const byDate = new Map();
    for (const reading of readings?.readings ?? []) {
      const value = reading.values[field];
      if (value === undefined || value === null) continue;
      const entry = byDate.get(reading.date) ?? { sum: 0, count: 0 };
      entry.sum += value;
      entry.count += 1;
      byDate.set(reading.date, entry);
    }
    const points = [...byDate.entries()]
      .sort(([a], [b]) => (a < b ? -1 : 1))
      .map(([date, { sum, count }]) => ({ x: parseIsoDate(date), y: (sum / count) * scale }));
    return { id: field, label, points };
  });
}

/** Daily readings of one field as rows over every date in the range. */
export function readingRows(readings, field, start, end, scale = 1) {
  const byDate = new Map(
    (readings?.readings ?? [])
      .filter((reading) => reading.values[field] !== undefined)
      .map((reading) => [reading.date, reading.values[field] * scale]),
  );
  return datesBetween(start, end).map((day) => ({
    key: day,
    day,
    x: parseIsoDate(day),
    value: byDate.get(day) ?? null,
  }));
}

/** Readings as a band: a middle value between a lower and an upper one. */
export function readingBandRows(readings, fields, start, end) {
  const byDate = new Map((readings?.readings ?? []).map((reading) => [reading.date, reading]));
  return datesBetween(start, end).map((day) => {
    const values = byDate.get(day)?.values ?? {};
    return {
      key: day,
      day,
      x: parseIsoDate(day),
      low: values[fields.low] ?? null,
      mid: values[fields.mid] ?? null,
      high: values[fields.high] ?? null,
    };
  });
}

export function hasReadings(readings) {
  return (readings?.readings ?? []).length > 0;
}

/** Hour-of-day by day: `[{ id: day, data: [{ x: "00", y }] }]`, newest first. */
export function hourByDay(series, start, end, pick) {
  const found = byKey(series?.buckets);
  return datesBetween(start, end)
    .reverse()
    .map((day) => ({
      id: day,
      data: Array.from({ length: 24 }, (_, hour) => {
        const bucket = found.get(`${day}T${pad(hour)}:00`);
        return { x: pad(hour), y: bucket ? pick(bucket) : null };
      }),
    }));
}

// --- sleep -------------------------------------------------------------------

export const SLEEP_STAGES = ["DEEP", "LIGHT", "REM", "AWAKE"];

/** Hours in each stage per day, every session on that day added together. */
export function sleepStageRows(sleep, start, end) {
  const byDate = new Map((sleep?.days ?? []).map((day) => [day.date, day]));
  return datesBetween(start, end).map((day) => {
    const row = { key: day, day, x: parseIsoDate(day) };
    for (const stage of SLEEP_STAGES) row[stage] = 0;
    for (const session of byDate.get(day)?.sessions ?? []) {
      for (const [stage, minutes] of Object.entries(session.stage_minutes)) {
        if (stage in row) row[stage] += minutes / 60;
      }
    }
    return row;
  });
}

// Bedtimes and wake times are measured from noon, so a night does not wrap
// past midnight: 23:00 is 11, 07:00 is 19.
const NOON = 12;

function hoursFromNoon(date, sessionDay) {
  const dayStart = parseIsoDate(sessionDay);
  dayStart.setDate(dayStart.getDate() - 1);
  dayStart.setHours(NOON, 0, 0, 0);
  return (date - dayStart) / 3_600_000;
}

/**
 * The main sleep of each night as a floating bar: an invisible lead-in up to
 * bedtime, then the time asleep. Values are offset by `base` so the scale can
 * start at zero; add it back to read a clock time.
 */
export function sleepTimingRows(sleep, start, end) {
  const byDate = new Map((sleep?.days ?? []).map((day) => [day.date, day]));
  const nights = datesBetween(start, end).map((day) => {
    const main = (byDate.get(day)?.sessions ?? []).find((session) => session.main_sleep);
    if (!main?.start || !main?.end) return { key: day, day, x: parseIsoDate(day), bed: null, wake: null };
    return {
      key: day,
      day,
      x: parseIsoDate(day),
      bed: hoursFromNoon(parseLocal(main.start), day),
      wake: hoursFromNoon(parseLocal(main.end), day),
    };
  });
  const known = nights.filter((night) => night.bed !== null);
  const base = known.length ? Math.floor(Math.min(...known.map((n) => n.bed))) - 1 : 0;
  const top = known.length ? Math.ceil(Math.max(...known.map((n) => n.wake))) + 1 : 1;
  const rows = nights.map((night) => ({
    ...night,
    lead: night.bed === null ? 0 : night.bed - base,
    asleep: night.bed === null ? 0 : night.wake - night.bed,
  }));
  return { rows, base, top: top - base };
}

/** Hours from noon back to a clock time, for the sleep timing axis. */
export function noonHoursToClock(hours) {
  return hours + NOON;
}

const STAGE_LEVEL = { AWAKE: 3, REM: 2, LIGHT: 1, DEEP: 0 };
export const STAGE_BY_LEVEL = ["Deep", "Light", "REM", "Awake"];

/** A session's stages as step-line points: stage level against time. */
export function hypnogramPoints(session) {
  const points = [];
  for (const stage of session.stages) {
    const level = STAGE_LEVEL[stage.stage];
    if (level === undefined || !stage.start) continue;
    points.push({ x: parseLocal(stage.start), y: level });
  }
  const last = session.stages.at(-1);
  if (last?.end && points.length) points.push({ x: parseLocal(last.end), y: points.at(-1).y });
  return points;
}

// --- exercise ----------------------------------------------------------------

export const RUNNING = "RUNNING";
const ZONE_WEIGHTS = { LIGHT: 1, MODERATE: 2, VIGOROUS: 3, PEAK: 4 };
export const EXERCISE_ZONES = ["LIGHT", "MODERATE", "VIGOROUS", "PEAK"];

/**
 * How hard a session was. Google's Active Zone Minutes when it sent them,
 * otherwise minutes in each heart-rate zone weighted 1 to 4 by zone.
 */
export function sessionLoad(session) {
  const azm = session.metrics?.active_zone_minutes;
  if (azm !== undefined && azm !== null) return { value: azm, source: "Active Zone Minutes" };
  let weighted = 0;
  for (const [zone, minutes] of Object.entries(session.zone_minutes ?? {})) {
    weighted += (ZONE_WEIGHTS[zone] ?? 0) * minutes;
  }
  return { value: weighted, source: "weighted zone minutes" };
}

/** Pace in minutes per kilometre, from Google's seconds per metre. */
export function paceMinutesPerKm(session) {
  const secondsPerMeter = session.metrics?.average_pace_seconds_per_meter;
  return secondsPerMeter ? (secondsPerMeter * 1000) / 60 : null;
}

/** Exercise types by how many sessions each has, most first. */
export function exerciseTypesByCount(sessions) {
  const counts = new Map();
  for (const session of sessions) {
    const type = session.exercise_type ?? "OTHER";
    counts.set(type, (counts.get(type) ?? 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([type]) => type);
}

/** Minutes of exercise per day. */
export function exerciseMinuteRows(sessions, start, end) {
  const minutes = new Map();
  for (const session of sessions) {
    if (!session.date) continue;
    minutes.set(session.date, (minutes.get(session.date) ?? 0) + session.duration_minutes);
  }
  return datesBetween(start, end).map((day) => ({
    key: day,
    day,
    x: parseIsoDate(day),
    value: minutes.get(day) ?? 0,
  }));
}

/** Monday-started weeks overlapping the range, oldest first. */
function weeksOf(start, end) {
  const weeks = [];
  for (let week = weekStart(start); week < end; week = addDays(week, 7)) weeks.push(week);
  return weeks;
}

/** Total and longest run distance per week, in kilometres. */
export function weeklyDistanceRows(runs, start, end) {
  const weeks = new Map(weeksOf(start, end).map((week) => [week, { total: 0, longest: 0 }]));
  for (const run of runs) {
    if (!run.date || !run.distance_meters) continue;
    const entry = weeks.get(weekStart(run.date));
    if (!entry) continue;
    const km = run.distance_meters / 1000;
    entry.total += km;
    entry.longest = Math.max(entry.longest, km);
  }
  return [...weeks.entries()].map(([week, { total, longest }]) => ({
    key: week,
    day: week,
    x: parseIsoDate(week),
    value: total,
    longest,
  }));
}

/** Share of each week's run time spent in each heart-rate zone, in percent. */
export function weeklyZoneShareRows(runs, start, end) {
  const weeks = new Map(
    weeksOf(start, end).map((week) => [week, Object.fromEntries(EXERCISE_ZONES.map((z) => [z, 0]))]),
  );
  for (const run of runs) {
    if (!run.date) continue;
    const entry = weeks.get(weekStart(run.date));
    if (!entry) continue;
    for (const zone of EXERCISE_ZONES) entry[zone] += run.zone_minutes?.[zone] ?? 0;
  }
  return [...weeks.entries()].map(([week, minutes]) => {
    const total = EXERCISE_ZONES.reduce((sum, zone) => sum + minutes[zone], 0);
    const row = { key: week, day: week, x: parseIsoDate(week), totalMinutes: total };
    for (const zone of EXERCISE_ZONES) row[zone] = total ? (minutes[zone] / total) * 100 : 0;
    return row;
  });
}

/** The mean of each point and up to `window - 1` before it. */
export function rollingMean(points, window) {
  return points.map((point, index) => {
    const slice = points.slice(Math.max(0, index - window + 1), index + 1);
    return { x: point.x, y: slice.reduce((sum, p) => sum + p.y, 0) / slice.length };
  });
}

/** Timed periods as lane spans, in minutes since midnight. */
export function periodSpans(periods, detail) {
  return periods
    .filter((period) => period.start && period.end)
    .map((period) => {
      const start = parseLocal(period.start);
      const end = parseLocal(period.end);
      const from = minutesOfDay(start);
      // A period that runs past midnight is drawn to the end of the day.
      const to = end.getDate() !== start.getDate() ? 1440 : minutesOfDay(end);
      const minutes = period.minutes ?? period.duration_minutes ?? (end - start) / 60_000;
      return { from, to: Math.max(to, from + 1), start, end, minutes, detail: detail?.(period) };
    });
}

/**
 * One lane per category over a single day: back-to-back buckets with minutes
 * in the category merge into one block, so an hour of five-minute "light"
 * buckets reads as one hour of light.
 */
export function categoryLanes(series, categories, resolution) {
  const step = RESOLUTION_MINUTES[resolution];
  const buckets = [...(series?.buckets ?? [])].sort((a, b) => (a.start < b.start ? -1 : 1));
  return categories.map((category) => {
    const spans = [];
    let current = null;
    for (const bucket of buckets) {
      const minutes = bucket.totals[category] ?? 0;
      const start = parseLocal(bucket.start);
      const from = minutesOfDay(start);
      if (!minutes) {
        current = null;
        continue;
      }
      if (current && current.to === from) {
        current.to = from + step;
        current.end = new Date(start.getTime() + step * 60_000);
        current.minutes += minutes;
      } else {
        current = {
          from,
          to: from + step,
          start,
          end: new Date(start.getTime() + step * 60_000),
          minutes,
        };
        spans.push(current);
      }
    }
    return { category, spans };
  });
}

/** Rows whose values are all zero or null draw nothing. */
export function allEmpty(rows, keys) {
  return rows.every((row) => keys.every((key) => !row[key]));
}
