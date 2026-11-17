# Charting

Part of the [health-cloud design context](CONTEXT.md). How the dashboard in
`client/` turns the read API into charts: the home page, the tabs, the
controls, every chart and why it was chosen, the colour rules, and what was
deferred or turned down.

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
- Every **5 minutes**, and on the refresh button, what is on screen
  re-fetches; everything else held is marked stale and re-fetches when next
  shown.
- Once every chart on the open tab has its data, the other tabs' views over
  the same span are fetched in the background, cheapest first, two at a time,
  so switching tabs usually shows data straight away. The raw-sample routes are
  skipped. The home page preloads nothing; its tiles fetch only what they show.
- **Memory only.** Nothing is written to `localStorage` or IndexedDB: that would
  leave decrypted health values on disk and undo
  [encryption at rest](encryption.md). A reload starts empty.

The refresh indicator is its own component, subscribed to the store, so a
request finishing re-renders it and the charts that use that data, not the whole
dashboard. Re-rendering every chart on every response froze the page.

## Pages

Three levels, each a history entry, so the browser's back button climbs back
up:

1. **Home:** the day's most telling figures as tiles. The default page.
2. **A group:** one tab's charts as compact previews, opened from a tile, from
   "← Home", or from the tab row.
3. **A chart:** one card in full, opened by clicking its preview.

## Home page

One day, today by default, with ‹ › arrows and a date picker. Ten tiles in two
groups, activity first:

| Group | Tiles |
| --- | --- |
| **Activity** (the last 24 hours on today, else that day) | steps, distance, Active Zone Minutes, heart-rate average |
| **Recovery** (overnight) | sleep, resting heart rate, nightly HRV, skin temperature, breathing rate, nightly blood oxygen |

- **The figure** is that day's value. On **today**, steps, distance, Active Zone
  Minutes and heart-rate average cover the **last 24 hours** instead, so a
  morning is not compared with whole days; the Activity heading says so. Skin temperature is the night's difference from the
  personal baseline Google reports.
- **The comparison** is against the **average of the seven complete days
  before**: a chip at the top right with an ▲/▼ and the difference, blue where
  that direction is usually better and orange where it is usually worse, grey
  where neither is (heart-rate average, breathing rate). A difference too small
  to show at the tile's precision reads "= usual". Skin temperature has no
  chip, since it is already a difference. The average itself is printed under
  the figure.
- **A bar** under each figure. Totals (steps, distance, Active Zone Minutes)
  **fill up from zero**, full at the week's best day or at the day itself when
  it beats it. Every other tile shows the day against the **personal range**:
  the same 10th-to-90th percentile of the 30 days before that the charts draw,
  as a green band, with the day as a dot, the 7-day average as a tick, and a
  caption giving the range in figures. The dot is in the tile's colour inside
  the range, and blue or orange outside it by which side is usually better. The
  six overnight tiles read 30 days of their daily routes for it. The heart-rate
  average reads the earlier days in a second, daily-bucket request, since they
  are a month of raw samples until step 8a: its figure shows first and its
  range when that lands. A tile with under 14 days of history shows the past
  week's lowest to highest in grey instead.
- **Layout:** column counts that divide each group evenly, so no row ends on a
  lone tile: the four Activity tiles in one row, the six Recovery tiles three by
  two, both two across on a medium page and one on a phone. On a wide page the
  three rows fill the screen below the controls exactly, the figures growing
  with the window's height, so the whole day reads without scrolling.
- **An icon** from `@mui/icons-material` per tile, in the colour of its chart.
- **Clicking a tile** opens its group on that day, scrolls to the matching card
  and outlines it briefly. Where the day view has no such card, the group opens
  at the top.
- Each tile has its **own loading, empty ("No data yet") and error state.**
- **Data** comes from the existing routes over the day and the seven before it;
  the Activity tiles and heart-rate average read hourly buckets so the last 24
  hours can be cut from them. The heart-rate average reads about eight days of
  raw samples, so it arrives last; the hourly summaries of step 8a make it
  cheap.

## Previews and the chart page

On a group page every card is a **preview**: smaller, without its note, sub-tabs,
legend, "Learn more", dashed reference lines or ringed extremes. The personal
range band and its marks stay. Clicking a preview opens its **chart page**: the
card, and any other card on the tab measuring the same thing (steps bars, steps
by hour and the steps calendar together), full width and taller, with
everything back. A card is named by its `explain` key, which is also what a home
tile scrolls to. A chart page whose cards have nothing at the chosen span says
so.

Previews are all one size and fill every row: three across on a wide page, two
on a medium one, one on a phone. When the count does not divide evenly the last
cards widen rather than leave one alone on a row: four become two and two, and
a remainder of two shares the row half and half. Only a tab with a single card
shows it on a row by itself. A card stretched by a taller neighbour in its row grows its
chart to fill the space; the height a card asks for is its minimum.

## Tabs and grouping

Routes are grouped by what they measure, one tab each. Only the open tab's
charts render.

| Tab | Routes |
| --- | --- |
| **Heart** | heart rate, resting heart rate, HRV, nightly HRV, zone limits, time in zone |
| **Sleep** | sleep sessions and stages, skin temperature, breathing rate per stage |
| **Breathing & oxygen** | SpO₂, nightly SpO₂, daily breathing rate |
| **Activity** | steps, distance, floors, activity level, Active Zone Minutes, sedentary periods |
| **Exercise** | exercise sessions, then the runs among them |
| **Food & body** | nutrition, hydration, height, VO₂ max, run VO₂ max |

Runs share the Exercise tab: they are exercise sessions from the same route,
filtered to `exercise_type` `RUNNING`, and a tab of their own added a click
without adding anything to read. They are recorded by the watch (`FITBIT`
source) with pace, distance and zone minutes. The same runs also arrive from
Nike Run Club through `HEALTH_KIT`, which reads drop, so nothing is counted
twice.

## Controls

The view lives in the query string (`group`, `chart`, `span`, `day`, `from`,
`bucket`, `res`), so a reload or a shared link lands on the same view. No
`group` is the home page; no `day` is today.

- **Span:** Day / Week / Month / 3 months, the last 1, 7, 30 or 90 days **ending
  on the chosen day**, or **Custom**: a From and a To date picker, at most 90
  days apart, so the raw-sample routes stay bounded until step 8a. `end` is sent
  as the day after the last one shown, because the API excludes it.
- **The chosen day** moves with the ‹ › arrows, by the span's length, or with
  the date picker. Clicking a day on any chart switches to Day on that date.
- **Bucket size:** hourly / daily, offered only for spans of seven days or
  fewer; longer spans are always daily, so a long span never asks for hundreds
  of thousands of samples. It changes only the routes that take a `resolution`;
  the rest are always daily. The hour-by-day heatmaps therefore appear at a
  week or less only.
- **A single day** has its own bucket size: 1 min / 5 / 10 / 30 min / 1 hour,
  defaulting to 1 hour.
- **Defaults:** a week, hourly, ending today.

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
- **On the chart page only:** the reference lines, extremes, legend and
  "Learn more" below; previews leave them out.
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

Each card uses the form that fits its data, so the tab is not six bar charts in
a row.

- **Steps:** bars, the one place a bar chart is the right form: comparing one
  day's count with another's. At daily buckets a solid line runs through them at
  the average of the last 7 days with steps, so the trend shows through the
  day-to-day noise; hourly buckets get no average. On a day, a **running total**
  line instead, which climbs on a walk and flattens while sitting.
- **Distance:** a **running total** line over the span, or through the day. Daily
  distance mostly repeats steps; the total answers a different question ("how far
  this month"). No reference lines: the average or maximum of a running total
  means nothing. The bucket's own amount shows on hover.
- **Activity level:** a **stacked area** of hours a day (minutes an hour at
  hourly buckets) at each level, so the split and the total read at once.
  Very active sits on the baseline and sedentary, the largest, on top, so the
  thin active bands stay readable. Lanes on a day.
- **Active Zone Minutes:** a **heatmap**, one row per zone (fat burn, cardio,
  peak) and one column per day, one blue ramp darker for more minutes. Each row
  is named, so colour is never the only cue. Hourly data is summed to days.
  Lanes on a day.
- **Floors:** a **dot plot**, a dot at each day's count with a thin stem down to
  zero. Floors are small whole numbers, often zero, and a wall of bars hid the
  busy days.
- **Sitting still:** a **line** of hours a day, with the reference lines: the
  trend matters more than any one day. Lanes of idle periods on a day.
- **Steps by hour** (hourly buckets only): the same hour-by-day heatmap.
- **Steps calendar** (exactly 90 days: 3 months, or a 90-day custom span): one
  square a day, darker for more. Bars are unreadable at 90 days; a calendar
  shows weekly patterns.

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
- **Latest sessions:** a table, last on the tab.
- **On a day:** session lanes and the day's sessions, then the same for runs.

Then the running charts, on the same tab:

- **Runs:** the session swarm, runs only.
- **Pace:** min/km per run on an ordinary axis, so faster runs sit lower and
  improving pace reads as a falling line, with the mean of the last 5 runs.
- **Weekly distance:** km per Monday-started week, with a tick for the week's
  longest run.
- **Aerobic efficiency:** pace against average heart rate per run, older runs
  lighter. Fitter moves dots towards faster pace at the same heart rate.
- **Intensity by week:** share of each week's running time in each zone, as 100%
  stacked bars; most plans aim for about 80% easy.

### Food & body

- **Energy eaten**, **water:** bars. **VO₂ max**, **run VO₂ max:** lines.
  **Height:** a figure. **On a day:** totals, macros and the food log.

### Lanes

On a single day, minutes per category become lanes, one per category, midnight
to midnight. Back-to-back buckets with minutes in a category merge into one
block, so twelve five-minute "light" buckets read as one hour of light. Lanes
rather than one strip because a single bucket often spans two categories, and a
strip would have to hide one. Hovering a block shows its times and minutes.

The same lanes show idle periods on Activity, and sessions by type and runs on
Exercise.

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

- **Scores on the home page:** stress, recovery, strain and a sleep score,
  calculated from the measurements already stored, in a row of their own above
  the tiles. After the home page settles.
- **Recovery check:** each day's training load against the next morning's HRV.
  Noisy without months of data. Revisit with the ML work.
- **Expected values from an ML model:** expected lines or ranges overlaid on the
  charts, to show how a day compares with what was expected. Nothing is built
  for it; with nivo it is a series or a custom layer added later. See
  [Decisions](decisions.md#deferred).
- **Hourly heart-rate summaries** so long ranges stop reading raw samples:
  the next task, step 8a in [the build order](CONTEXT.md#build-order). Until
  then, raw heart rate, time in zone, HRV and SpO₂ samples, activity level and
  zone minutes are never preloaded, and the raw heart-rate chart has no
  personal range, because each would read hundreds of thousands of rows.
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
