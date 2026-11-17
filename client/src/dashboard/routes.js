// The routes each tab reads, as `[path, params]` pairs for a view. One list
// serves both the tab itself and the preloading of tabs not yet opened.

function bucketed(view) {
  return { start: view.start, end: view.end, resolution: view.resolution };
}

function plain(view) {
  return { start: view.start, end: view.end };
}

export const ROUTES = {
  heart: (view) => ({
    heartRate: ["/heart-rate", bucketed(view)],
    resting: ["/heart-rate/resting", plain(view)],
    zones: ["/heart-rate/zones", plain(view)],
    timeInZone: ["/heart-rate/time-in-zone", bucketed(view)],
    variability: ["/heart-rate/variability", bucketed(view)],
    variabilityDaily: ["/heart-rate/variability/daily", plain(view)],
  }),
  sleep: (view) => ({
    sleep: ["/sleep", plain(view)],
    temperature: ["/sleep/temperature", plain(view)],
    breathing: ["/respiratory-rate", plain(view)],
  }),
  breathing: (view) => ({
    oxygen: ["/oxygen-saturation", bucketed(view)],
    oxygenDaily: ["/oxygen-saturation/daily", plain(view)],
    breathing: ["/respiratory-rate/daily", plain(view)],
  }),
  activity: (view) => ({
    steps: ["/activity/steps", bucketed(view)],
    distance: ["/activity/distance", bucketed(view)],
    floors: ["/activity/floors", plain(view)],
    level: ["/activity/level", bucketed(view)],
    zoneMinutes: ["/activity/zone-minutes", bucketed(view)],
    sedentary: ["/activity/sedentary", plain(view)],
    // Only the 90-day calendar needs it; null skips the fetch.
    dailySteps: [
      "/activity/steps",
      view.mode === "range" && view.days === 90 ? { ...plain(view), resolution: "1d" } : null,
    ],
  }),
  exercise: (view) => ({
    exercise: ["/exercise", plain(view)],
  }),
  food: (view) => ({
    nutrition: ["/nutrition", plain(view)],
    hydration: ["/hydration", plain(view)],
    height: ["/body/height", plain(view)],
    vo2: ["/body/vo2-max", plain(view)],
    runVo2: ["/body/vo2-max/run", plain(view)],
  }),
};
