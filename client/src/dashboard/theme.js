// Chart colours and the nivo theme. Values mirror the custom properties in
// styles.css; nivo needs them as plain strings, not CSS variables.

export const INK = "#0f1c23";
export const INK_SOFT = "#566871";
export const RULE = "#c4cfd4";
export const SURFACE = "#f4f7f8";
export const EMPTY = "#dce3e6";
export const HOVER = "rgba(15, 28, 35, 0.07)";

// Each chart has a colour of its own, the same at every range and bucket size,
// and no two charts on one tab share one. Kept off the zone, stage and
// reference-line colours below where those share a tab.
export const CHART = {
  heartRate: "#d55181",
  resting: "#1d4e89",
  variability: "#eb6834",
  nightlyHrv: "#9a5b2e",
  deepSleepHrv: "#6b7f1a",
  nonRemHeartRate: "#c2417a",
  entropy: "#4f6d7a",

  sleepTiming: "#9a5b2e",
  breathingNight: "#d55181",

  oxygen: "#2a78d6",
  oxygenNightly: "#1d4e89",
  breathing: "#2f8f2f",

  steps: "#eb6834",
  distance: "#2a78d6",
  floors: "#9a5b2e",
  sedentary: "#4f6d7a",

  exerciseMinutes: "#2f8f2f",
  runs: "#eb6834",
  pace: "#d55181",
  weeklyDistance: "#2a78d6",

  energy: "#eb6834",
  water: "#2a78d6",
  vo2: "#2f8f2f",
  runVo2: "#d55181",
  height: "#4f6d7a",
};

// The intensity scale, the same wherever zones appear: light blue, moderate
// green, vigorous yellow, peak red. Every use also names the zone, so colour
// is never the only cue.
export const ZONE = {
  LIGHT: "#2a78d6",
  MODERATE: "#2f8f2f",
  VIGOROUS: "#e0a100",
  PEAK: "#e34948",
};
// Google's Active Zone Minutes name the same scale differently.
export const AZM_ZONE = { FAT_BURN: ZONE.MODERATE, CARDIO: ZONE.VIGOROUS, PEAK: ZONE.PEAK };
export const ACTIVITY_LEVEL = {
  SEDENTARY: "#8a979d",
  LIGHTLY_ACTIVE: ZONE.LIGHT,
  MODERATELY_ACTIVE: ZONE.MODERATE,
  VERY_ACTIVE: ZONE.PEAK,
};

export const STAGE = {
  DEEP: "#1d4e89",
  LIGHT: "#86b6ef",
  REM: "#6250d6",
  AWAKE: "#eb6834",
};

// The dashed reference lines every chart can show.
export const REFERENCE = {
  avg: "#3d4a50",
  max: "#7b3fbf",
  min: "#0f8b8d",
};

// Your personal range: a light green band, and the ring on a day outside it,
// blue on the good side and orange on the side to watch.
export const PERSONAL_BAND = "rgba(47, 143, 47, 0.14)";
export const PERSONAL_SWATCH = "#9ccf9c";
export const PERSONAL_TONE = { good: "#2a78d6", watch: "#e5761f" };

export const FELL_ASLEEP = "#6250d6";
export const WOKE_UP = "#e0a100";

// Categorical slots for things with no fixed colour, such as exercise types.
export const SERIES = ["#2a78d6", "#eb6834", "#1baf7a"];
export const OTHER = "#8a979d";

// One hue, light to dark, for magnitude: heatmap cells, calendar days.
export const SEQUENTIAL = [
  "#cde2fb",
  "#9ec5f4",
  "#6da7ec",
  "#3987e5",
  "#256abf",
  "#184f95",
  "#0d366b",
];

// Two poles for a value either side of a baseline.
export const BELOW = "#2a78d6";
export const ABOVE = "#e34948";

export const nivoTheme = {
  background: "transparent",
  text: {
    fontFamily: '"IBM Plex Sans", system-ui, sans-serif',
    fontSize: 12,
    fill: INK_SOFT,
  },
  axis: {
    domain: { line: { stroke: "transparent" } },
    ticks: {
      line: { stroke: RULE, strokeWidth: 1 },
      text: { fill: INK_SOFT, fontSize: 12 },
    },
    legend: { text: { fill: INK_SOFT, fontSize: 12 } },
  },
  grid: { line: { stroke: RULE, strokeWidth: 1, strokeOpacity: 0.6 } },
  crosshair: { line: { stroke: INK, strokeWidth: 1, strokeOpacity: 0.5 } },
  tooltip: {
    container: {
      background: "#ffffff",
      color: INK,
      fontSize: 13,
      borderRadius: 2,
      boxShadow: "0 2px 10px rgba(15, 28, 35, 0.18)",
      padding: "7px 10px",
    },
  },
};

/** The sequential step for `value` between `min` and `max`. */
export function sequentialColor(value, min, max) {
  if (value === null || value === undefined) return EMPTY;
  const span = max - min || 1;
  const position = Math.min(Math.max((value - min) / span, 0), 1);
  return SEQUENTIAL[Math.min(Math.floor(position * SEQUENTIAL.length), SEQUENTIAL.length - 1)];
}
