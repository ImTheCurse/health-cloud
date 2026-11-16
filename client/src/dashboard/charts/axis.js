// Axis ticks shared by the charts: few enough labels to read, on round times.

import { formatDay, formatTime } from "../format.js";

const DAY_MS = 86_400_000;

/** Tick spacing and label format for a time axis spanning `from`..`to`. */
export function timeAxis(from, to) {
  const days = (to - from) / DAY_MS;
  if (days <= 1.01) return { tickValues: "every 3 hours", format: formatTime };
  if (days <= 2.01) return { tickValues: "every 6 hours", format: formatTime };
  if (days <= 8) return { tickValues: "every 1 day", format: formatDay };
  if (days <= 31) return { tickValues: "every 5 days", format: formatDay };
  return { tickValues: "every 14 days", format: formatDay };
}

/**
 * Which rows of a bar chart get a label. Within one day, labels fall on whole
 * three-hour marks; across days, sub-daily rows are labelled at midnight only.
 * Either way they are thinned to at most `max`.
 */
export function barTicks(rows, max = 8) {
  let candidates = rows;
  if (isSingleDay(rows)) {
    candidates = rows.filter((row) => /T(00|03|06|09|12|15|18|21):00$/.test(row.key));
  } else if (rows.length > 48) {
    candidates = rows.filter((row) => row.key.endsWith("T00:00"));
  }
  const step = Math.max(1, Math.ceil(candidates.length / max));
  return candidates.filter((_, index) => index % step === 0).map((row) => row.key);
}

/** The label of a bar row: a time within one day, otherwise the date. */
export function barLabel(row, rows) {
  return isSingleDay(rows) ? formatTime(row.x) : formatDay(row.x);
}

function isSingleDay(rows) {
  return rows.length > 1 && rows[0].day === rows.at(-1).day;
}

/** Height for `days` rows, so cells stay legible however long the range. */
export function heatmapHeight(days) {
  return 30 + Math.max(days, 4) * (days > 31 ? 9 : 22);
}
