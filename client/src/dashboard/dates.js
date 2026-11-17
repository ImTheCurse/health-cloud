// Every date here is a civil date on the browser's clock, as "YYYY-MM-DD".
// The API speaks the same local clock, with no timezone on its timestamps.

const pad = (n) => String(n).padStart(2, "0");

export function isoDate(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function parseIsoDate(iso) {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day);
}

export function addDays(iso, days) {
  const date = parseIsoDate(iso);
  date.setDate(date.getDate() + days);
  return isoDate(date);
}

export function today() {
  return isoDate(new Date());
}

/** One day, as a half-open range. */
export function dayRange(day) {
  return { start: day, end: addDays(day, 1) };
}

/** Every date from `start` up to, not including, `end`. */
export function datesBetween(start, end) {
  const dates = [];
  for (let day = start; day < end; day = addDays(day, 1)) dates.push(day);
  return dates;
}

/**
 * A timestamp from the API, read on the local clock. The API sends no offset,
 * which JavaScript already reads as local; the fraction is cut to milliseconds
 * because the API sends microseconds.
 */
export function parseLocal(timestamp) {
  return timestamp ? new Date(timestamp.slice(0, 23)) : null;
}

/** "YYYY-MM-DDTHH:MM" of a local timestamp: the key a bucket is stored under. */
export function minuteKey(timestamp) {
  return timestamp.slice(0, 16);
}

/** The Monday starting the week that holds `iso`. */
export function weekStart(iso) {
  const date = parseIsoDate(iso);
  const sinceMonday = (date.getDay() + 6) % 7;
  return addDays(iso, -sinceMonday);
}

/** Minutes since local midnight. */
export function minutesOfDay(date) {
  return date.getHours() * 60 + date.getMinutes() + date.getSeconds() / 60;
}
