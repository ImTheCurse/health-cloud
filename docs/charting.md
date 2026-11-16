# Charting

Part of the [health-cloud design context](CONTEXT.md). How the dashboard in
`client/` turns the read API into charts: the tabs, the controls, every chart
and why it was chosen, the colour rules, and what was deferred or turned down.

## Stack

- **nivo** (`@nivo/line`, `bar`, `heatmap`, `calendar`, `swarmplot`,
  `scatterplot`) draws every chart. Custom SVG layers add what nivo lacks: the
  reference lines, hover column, zone bands, sleep-stage step line, longest-run
  ticks and midnight lines.
- **MUI** (`@mui/material`, `@mui/x-date-pickers` with `dayjs`) supplies every
  control: tabs, toggle groups, the date picker, icon buttons, the "Learn more"
  dialog and the lane tooltips. It is restyled in `client/src/dashboard/muiTheme.js`
  to the page's paper-and-ink look, never used with default Material styling.
  Prefer an existing library component to a hand-built control.
- Plain JavaScript, no TypeScript; data fetching through `api.js`, no fetching
  library.

## Data and caching

Each tab's routes are listed once in `routes.js`, and the tab and the
background preloading both read from that list.

Responses live in an in-memory store (`dataStore.js`) for as long as the tab is
open:

- A chart asking for data already held gets it immediately.
- A refresh re-fetches in the background and swaps the new data in; the chart
  never goes back to "Loading…". A failed refresh keeps the data on screen.
- Everything held refreshes every **5 minutes**, and on the refresh button.
- After the open tab loads, every other tab's range view is fetched in the
  background, so switching tabs shows data straight away.
- **Memory only.** Nothing is written to `localStorage` or IndexedDB: that would
  leave decrypted health values on disk and undo
  [encryption at rest](encryption.md). A reload starts empty.

The refresh indicator is its own component, subscribed to the store, so a
request finishing re-renders it and the charts that use that data, not the whole
dashboard. Re-rendering every chart on every response froze the page.

## Tabs and grouping

Routes are grouped by what they measure, one tab each. Only the open tab's
charts render.

| Tab | Routes |
| --- | --- |
| **Heart** | heart rate, resting heart rate, HRV, nightly HRV, zone limits, time in zone |
| **Sleep** | sleep sessions and stages, skin temperature, breathing rate per stage |
| **Breathing & oxygen** | SpO₂, nightly SpO₂, daily breathing rate |
| **Activity** | steps, distance, floors, activity level, Active Zone Minutes, sedentary periods |
| **Exercise** | exercise sessions |
| **Running** | exercise sessions where `exercise_type` is `RUNNING` |
| **Food & body** | nutrition, hydration, height, VO₂ max, run VO₂ max |

Running is its own tab because runs are recorded by the watch (`FITBIT` source)
with pace, distance and zone minutes. The same runs also arrive from Nike Run
Club through `HEALTH_KIT`, which reads drop, so nothing is counted twice.

## Controls

The view lives in the query string (`group`, `range`, `bucket`, `day`, `res`),
so a reload or a shared link lands on the same view, and the browser's back
button leaves a day.

- **Range:** 7 / 30 / 90 days, ending today in the browser's local date.
  `end` is sent as tomorrow, because the API excludes it.
- **Bucket size:** hourly / daily. It changes only the routes that take a
  `resolution`; the rest are always daily.
- **Default:** 7 days, hourly.
- **A single day** opens from the date picker, the ‹ › arrows, or by clicking a
  day on any chart. It has its own bucket size: 1 min / 5 / 10 / 30 min / 1 hour,
  defaulting to 1 hour.

## On every chart

- **Reference lines:** dashed average, max and min of what is on screen, in
  fixed colours: dark grey for average, purple for max, teal for min. Each is
  labelled at the right, labels pushed apart when lines are close. For stacked
  bars they track the bar total; with several lines, the first visible line.
  Charts where they mislead leave them out: sleep timing, temperature
  deviation, intensity shares, the stage step line.
- **Extremes:** the max and min points are ringed and labelled with their value.
- **Bars count only buckets with data** toward the statistics: an empty hour is
  a gap in the record, not a measured zero.
- **Legend toggles:** every series, and each reference line, switches on and off
  from the legend.
- **Hover:** a soft column behind the hovered time or bar, a halo behind a
  hovered dot, and a tooltip with the exact value.
- **Learn more:** a dialog per chart (`explain.js`) saying what the measurement
  is, how the watch gets it, and which way is usually better, ending with a
  not-medical-advice line.
- **Own states:** each card shows its own loading, empty or error state, so one
  failing route blanks only its card.

## Charts

### Heart

- **Heart rate:** the bucket mean as a line; the bucket's own range shows on
  hover. On a day, heart-rate zones are shaded behind it.
- **Heart rate by hour** (hourly buckets only): hour of day across, one row per
  day, one hue darker for higher. Shows the daily rhythm at a glance.
- **Resting heart rate**, **non-REM heart rate**, **HRV entropy:** one line each.
- **Heart-rate variability:** bucket mean as a line, with its dashed average.
- **Nightly HRV:** the night average and deep-sleep RMSSD, two lines, one unit.
- **Time in heart-rate zone:** over a range, one sub-tab per zone comparing that
  zone's minutes across the days; on a day, see [Lanes](#lanes).
- **Heart-rate zones:** the latest limits as figures.

### Sleep

- **Sleep:** hours per night stacked by stage, naps folded into the day the sleep
  ended.
- **Sleep timing:** a floating bar per night from falling asleep to waking, on a
  clock axis measured from noon so a night does not wrap past midnight. A dot
  marks each start and each end. Even bars mean a steady schedule.
- **Skin temperature:** each night minus the baseline, as diverging bars, red
  above and blue below, on a scale symmetric around zero.
- **Breathing rate in sleep:** the whole night and each stage, stages in their
  stage colours.
- **On a day:** a step line through the stages, each stretch in its stage
  colour, plus that night's summary figures.

### Breathing & oxygen

- **Blood oxygen:** bucket mean as a line.
- **Nightly blood oxygen:** Google's nightly average; the lower and upper bound
  show on hover.
- **Breathing rate:** one line, a figure a day.

### Activity

- **Steps**, **distance**, **floors**, **sitting still:** bars.
- **Steps by hour** (hourly buckets only): the same hour-by-day heatmap.
- **Steps calendar** (90 days only): one square a day, darker for more. Bars are
  unreadable at 90 days; a calendar shows weekly patterns.
- **Activity level** and **Active Zone Minutes:** sub-tabs over a range, lanes on
  a day.

### Exercise

- **Sessions:** a swarm, one dot per session along time. Dot **area** grows
  with load, so radius grows with its square root, and diameter is capped at
  7–26 px so one hard session cannot cover its week. Colour is the type: the
  three most frequent types get a hue each, the rest share "other". Dotted lines
  mark midnight, Mondays only past 31 days.
- **Load** is Google's Active Zone Minutes for the session. Google sends no
  cardio-load figure, so where AZM is missing, load is minutes in each
  heart-rate zone weighted 1 (light) to 4 (peak), the usual zone-based
  training-load estimate.
- **Minutes of exercise:** bars.
- **Latest sessions:** a table.
- **On a day:** session lanes and the day's sessions.

### Running

- **Runs:** the session swarm, runs only.
- **Pace:** min/km per run, faster at the top, with the mean of the last 5 runs.
- **Weekly distance:** km per Monday-started week, with a tick for the week's
  longest run.
- **Aerobic efficiency:** pace against average heart rate per run, older runs
  lighter. Fitter moves dots towards faster pace at the same heart rate.
- **Intensity by week:** share of each week's running time in each zone, as 100%
  stacked bars; most plans aim for about 80% easy.
- **On a day:** run lanes and the day's runs.

### Food & body

- **Energy eaten**, **water:** bars. **VO₂ max**, **run VO₂ max:** lines.
  **Height:** a figure. **On a day:** totals, macros and the food log.

### Lanes

On a single day, minutes per category become lanes, one per category, midnight
to midnight. Back-to-back buckets with minutes in a category merge into one
block, so twelve five-minute "light" buckets read as one hour of light. Lanes
rather than one strip because a single bucket often spans two categories, and a
strip would have to hide one. Hovering a block shows its times and minutes.

The same lanes show idle periods on Activity, and sessions by type on Exercise
and Running.

## Colour

Colours live in `client/src/dashboard/theme.js`.

- **Each chart has its own colour,** kept the same at every range and bucket
  size, and no two charts on one tab share one.
- **Zones always use the same scale:** light blue, moderate green, vigorous
  yellow, peak red. Google's Active Zone Minutes map fat burn to green, cardio
  to yellow and peak to red. Activity levels use sedentary grey, light blue,
  moderate green and very active red. Red and green are hard to tell apart for
  many people, so every zone also carries its name in the sub-tab, lane and
  tooltip: colour is never the only cue.
- **Sleep stages:** deep dark blue, light pale blue, REM violet, awake orange,
  in the bars, the stage step line and the breathing-by-stage lines alike.
- **Magnitude** (heatmaps, the calendar, older-to-newer runs) uses one blue
  ramp, light to dark.

## Deferred

- **Recovery check:** each day's training load against the next morning's HRV.
  Noisy without months of data. Revisit with the ML work.
- **Expected values from an ML model:** expected lines or ranges overlaid on the
  charts, to show how a day compares with what was expected. Nothing is built
  for it; with nivo it is a series or a custom layer added later. See
  [Decisions](decisions.md#deferred).
- **A table view per chart,** for reading exact values without hovering.
- **Splitting the bundle per tab.** nivo and MUI make the production bundle
  about 1.1 MB (350 KB gzipped). Fine for one self-hosted user; split if it
  becomes a problem.

## Rejected

| Proposal | Why not |
| --- | --- |
| Shaded lowest-to-highest band behind each line | Added clutter and no insight; the dashed max and min lines, and the bucket range on hover, say it better |
| Sleep-stage share donut | It repeats the stacked sleep bar |
| Fitness trend (run VO₂ max against resting heart rate) | Two measures on two y-axes misleads; both have their own chart already |
| Caching responses in `localStorage` | Leaves decrypted health values on disk |
| A charting library's default look, or hand-rolled controls | Use nivo and MUI, restyled to the page |

## Open decisions this touches

- [Combining sources](decisions.md#open-decisions): reads keep `FITBIT` and
  `GOOGLE_HEALTH` only, so Nike Run Club copies of runs are dropped.
- [How `client/` is served in production](decisions.md#open-decisions): due at
  step 10.
- [A table for daily summaries](decisions.md#open-decisions): not needed; the
  daily routes read fine from `unknown_data_points`.
