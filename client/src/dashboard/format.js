const dayFormat = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short" });
const longDayFormat = new Intl.DateTimeFormat(undefined, {
  weekday: "short",
  day: "numeric",
  month: "short",
});
const fullDayFormat = new Intl.DateTimeFormat(undefined, {
  weekday: "long",
  day: "numeric",
  month: "long",
  year: "numeric",
});
const timeFormat = new Intl.DateTimeFormat(undefined, {
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

export const formatDay = (date) => dayFormat.format(date);
export const formatLongDay = (date) => longDayFormat.format(date);
export const formatFullDay = (date) => fullDayFormat.format(date);
export const formatTime = (date) => timeFormat.format(date);
export const formatDayTime = (date) => `${formatLongDay(date)}, ${formatTime(date)}`;

const numberFormats = new Map();

export function formatNumber(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  if (!numberFormats.has(digits)) {
    numberFormats.set(
      digits,
      new Intl.NumberFormat(undefined, {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      }),
    );
  }
  return numberFormats.get(digits).format(value);
}

export function formatMinutes(minutes) {
  if (minutes === null || minutes === undefined) return "–";
  const whole = Math.round(minutes);
  const hours = Math.floor(whole / 60);
  const rest = whole % 60;
  if (hours === 0) return `${rest} min`;
  return rest === 0 ? `${hours} h` : `${hours} h ${rest} min`;
}

/** Minutes per kilometre as "m:ss". */
export function formatPace(minutesPerKm) {
  if (!minutesPerKm) return "–";
  let minutes = Math.floor(minutesPerKm);
  let seconds = Math.round((minutesPerKm - minutes) * 60);
  if (seconds === 60) {
    minutes += 1;
    seconds = 0;
  }
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

/** A clock time from hours since midnight, wrapping past 24. */
export function formatClockHours(hours) {
  const wrapped = ((hours % 24) + 24) % 24;
  const whole = Math.floor(wrapped);
  const minutes = Math.round((wrapped - whole) * 60);
  return `${String(whole).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

/** "WALKING" -> "Walking", "CARDIO_WORKOUT" -> "Cardio workout". */
export function humanize(name) {
  if (!name) return "Unknown";
  const words = name.toLowerCase().split("_");
  words[0] = words[0].charAt(0).toUpperCase() + words[0].slice(1);
  return words.join(" ");
}
