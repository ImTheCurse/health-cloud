import { useMemo } from "react";

import Card from "../Card.jsx";
import Bars from "../charts/Bars.jsx";
import DayHeatmap from "../charts/DayHeatmap.jsx";
import Lanes from "../charts/Lanes.jsx";
import Scatter from "../charts/Scatter.jsx";
import StackedArea from "../charts/StackedArea.jsx";
import { REFERENCE_KEYS } from "../charts/stats.js";
import StepsCalendar from "../charts/StepsCalendar.jsx";
import TimeLine from "../charts/TimeLine.jsx";
import { timeAxis } from "../charts/axis.js";
import { datesBetween, isoDate, parseIsoDate } from "../dates.js";
import { formatDay, formatMinutes, formatNumber } from "../format.js";
import {
  categoryDailyTotals,
  categoryRows,
  hasBuckets,
  periodSpans,
  presentCategories,
  readingRows,
  rollingAverage,
  runningTotal,
  sumRows,
} from "../series.js";
import { ROUTES } from "../routes.js";
import { ACTIVITY_LEVEL, AZM_ZONE, CHART, INK } from "../theme.js";
import { useData } from "../useData.js";
import { useHidden } from "../useHidden.js";
import { CategoryCard, Figures, HeatmapCard } from "./common.jsx";
import { useBounds } from "./view.js";

const LEVEL_ORDER = ["SEDENTARY", "LIGHTLY_ACTIVE", "MODERATELY_ACTIVE", "VERY_ACTIVE"];
const LEVEL_LABELS = {
  SEDENTARY: "Sedentary",
  LIGHTLY_ACTIVE: "Light",
  MODERATELY_ACTIVE: "Moderate",
  VERY_ACTIVE: "Very active",
};
// Stacked bottom to top: the active levels sit on the baseline, where they
// can be read, and sedentary, the largest, on top.
const LEVEL_STACK = ["VERY_ACTIVE", "MODERATELY_ACTIVE", "LIGHTLY_ACTIVE", "SEDENTARY"];
const AZM_ORDER = ["FAT_BURN", "CARDIO", "PEAK"];
// Days in the rolling average drawn over the daily steps.
const ROLLING_DAYS = 7;
const AZM_LABELS = { FAT_BURN: "Fat burn", CARDIO: "Cardio", PEAK: "Peak" };

const totalOf = (bucket) => bucket.total;
const formatSteps = (value) => `${formatNumber(value)} steps`;

export default function Activity({ view }) {
  const routes = ROUTES.activity(view);
  const steps = useData(...routes.steps);
  const dailySteps = useData(...routes.dailySteps);
  const distance = useData(...routes.distance);
  const floors = useData(...routes.floors);
  const level = useData(...routes.level);
  const zoneMinutes = useData(...routes.zoneMinutes);
  const sedentary = useData(...routes.sedentary);

  const stepTotal = useMemo(
    () => (steps.data?.buckets ?? []).reduce((sum, bucket) => sum + bucket.total, 0),
    [steps.data],
  );

  const levelCard =
    view.mode === "range" ? (
      <LevelCard state={level} view={view} />
    ) : (
      <CategoryCard
        title="Activity level"
        explain="activityLevel"
        state={level}
        view={view}
        order={LEVEL_ORDER}
        labels={LEVEL_LABELS}
        colors={ACTIVITY_LEVEL}
      />
    );
  const zoneCard =
    view.mode === "range" ? (
      <ZoneHeatmapCard state={zoneMinutes} view={view} />
    ) : (
      <CategoryCard
        title="Active Zone Minutes"
        note="Google's own count: cardio and peak minutes count double."
        explain="azm"
        state={zoneMinutes}
        view={view}
        order={AZM_ORDER}
        labels={AZM_LABELS}
        colors={AZM_ZONE}
      />
    );
  const stepsCard =
    view.mode === "range" ? (
      <StepsCard state={steps} view={view} />
    ) : (
      <RunningTotalCard
        title="Steps"
        note={`${formatNumber(stepTotal)} in total, building up through the day.`}
        explain="steps"
        state={steps}
        view={view}
        color={CHART.steps}
      />
    );
  const distanceCard = (
    <RunningTotalCard
      title="Distance"
      note="A running total: it climbs while you move and flattens while you rest."
      explain="distance"
      state={distance}
      view={view}
      scale={1 / 1000}
      digits={1}
      unit=" km"
      color={CHART.distance}
    />
  );

  if (view.mode === "day") {
    const day = sedentary.data?.days?.[0];
    const lanes = [
      {
        id: "sedentary",
        label: "Sitting still",
        color: CHART.sedentary,
        spans: periodSpans(day?.periods ?? []),
      },
    ];
    return (
      <>
        {stepsCard}
        {distanceCard}
        {levelCard}
        {zoneCard}
        <Card
          title="Sitting still"
          note={day ? `${formatMinutes(day.minutes)} in idle periods. Hover a block for its times.` : undefined}
          explain="sedentary"
          states={[sedentary]}
          empty={!day || day.periods.length === 0}
          height="auto"
          wide
        >
          <Lanes lanes={lanes} label="Idle periods across the day" />
        </Card>
        <Figures
          title="That day"
          explain="floors"
          states={[floors]}
          items={[{ label: "Floors climbed", value: floors.data?.readings?.[0]?.values.count ?? null }]}
          emptyText="No floors recorded."
        />
      </>
    );
  }

  return (
    <>
      {stepsCard}
      {view.days === 90 && <CalendarCard state={dailySteps} view={view} />}
      {view.resolution === "1h" && (
        <HeatmapCard
          title="Steps by hour"
          note="Darker is more. Click a row to open that day."
          explain="steps"
          state={steps}
          view={view}
          pick={totalOf}
          format={formatSteps}
        />
      )}
      {distanceCard}
      {levelCard}
      {zoneCard}
      <FloorsCard state={floors} view={view} />
      <SedentaryCard state={sedentary} view={view} />
    </>
  );
}

function CalendarCard({ state, view }) {
  const rows = useMemo(
    () => (state.data ? sumRows(state.data, view.start, view.end, "1d") : []),
    [state.data, view.start, view.end],
  );
  return (
    <Card
      title="Steps calendar"
      note="One square a day, darker for more steps."
      explain="steps"
      states={[state]}
      empty={!hasBuckets(state.data)}
      height={190}
      wide
    >
      <StepsCalendar rows={rows} start={view.start} end={view.end} onDay={view.onDay} />
    </Card>
  );
}

/**
 * Daily steps as bars, the anchor of the tab, with a rolling average through
 * them so the trend shows through the day-to-day noise. Hourly buckets get no
 * average: a seven-hour mean says nothing.
 */
function StepsCard({ state, view }) {
  const [hidden, toggle] = useHidden();
  const rows = useMemo(
    () => (state.data ? sumRows(state.data, view.start, view.end, view.resolution) : []),
    [state.data, view.start, view.end, view.resolution],
  );
  const daily = view.resolution === "1d";
  const rolling = useMemo(() => (daily ? rollingAverage(rows, ROLLING_DAYS) : []), [daily, rows]);
  const layers = useMemo(
    () => (daily && !hidden.has("rolling") ? [RollingLine(rolling)] : []),
    [daily, hidden, rolling],
  );
  const keys = useMemo(() => [{ key: "value", label: "Steps", color: CHART.steps }], []);
  const legend = daily
    ? [{ id: "rolling", label: `${ROLLING_DAYS}-day average`, color: INK, shape: "line" }, ...REFERENCE_KEYS]
    : REFERENCE_KEYS;
  return (
    <Card
      title="Steps"
      note={daily ? `The line is the average of the last ${ROLLING_DAYS} days with steps.` : undefined}
      explain="steps"
      states={[state]}
      empty={!hasBuckets(state.data)}
      legend={legend}
      hidden={hidden}
      onToggle={toggle}
    >
      <Bars rows={rows} keys={keys} hidden={hidden} format={formatSteps} layers={layers} onDay={view.onDay} />
    </Card>
  );
}

/** A line through the middle of each bar at its rolling average. */
function RollingLine(points) {
  return function Rolling({ xScale, yScale }) {
    const half = xScale.bandwidth() / 2;
    let path = "";
    let pen = false;
    for (const point of points) {
      if (point.value === null) {
        pen = false;
        continue;
      }
      path += `${pen ? "L" : "M"}${xScale(point.key) + half},${yScale(point.value)}`;
      pen = true;
    }
    return <path d={path} fill="none" stroke={INK} strokeWidth={2} strokeOpacity={0.8} pointerEvents="none" />;
  };
}

/**
 * A total building up through the view: through the day on a day, across the
 * days over a range. The bucket's own amount shows on hover. No reference
 * lines: the average or maximum of a running total means nothing.
 */
function RunningTotalCard({ title, note, explain, state, view, scale = 1, digits = 0, unit = "", color }) {
  const { from, to } = useBounds(view);
  const rows = useMemo(
    () => (state.data ? sumRows(state.data, view.start, view.end, view.resolution, scale) : []),
    [state.data, view.start, view.end, view.resolution, scale],
  );
  const points = useMemo(() => runningTotal(rows), [rows]);
  const series = useMemo(() => [{ id: "total", label: title, color, points }], [title, color, points]);
  const byTime = useMemo(() => new Map(points.map((point) => [point.x.getTime(), point])), [points]);
  const tipExtra = (x) => {
    const point = byTime.get(x.getTime());
    return point?.amount ? `+${formatNumber(point.amount, digits)}${unit} in this ${view.resolution === "1d" ? "day" : "bucket"}` : null;
  };
  return (
    <Card title={title} note={note} explain={explain} states={[state]} empty={!hasBuckets(state.data)}>
      <TimeLine
        series={series}
        from={from}
        to={to}
        unit={unit}
        digits={digits}
        daily={view.resolution === "1d"}
        references={false}
        tipExtra={tipExtra}
        onDay={view.mode === "range" ? view.onDay : undefined}
      />
    </Card>
  );
}

/** Time at each activity level, stacked, so the split and the day's total read at once. */
function LevelCard({ state, view }) {
  const { from, to } = useBounds(view);
  const [hidden, toggle] = useHidden();
  const daily = view.resolution === "1d";
  const series = useMemo(() => {
    if (!state.data) return [];
    const categories = presentCategories(state.data, LEVEL_STACK).filter((category) => LEVEL_STACK.includes(category));
    const rows = categoryRows(state.data, view.start, view.end, view.resolution, categories);
    // Stop at the last bucket with anything in it, as today's hours to come are empty.
    let last = -1;
    rows.forEach((row, index) => {
      if (categories.some((category) => row[category])) last = index;
    });
    const shown = rows.slice(0, last + 1);
    return categories.map((category) => ({
      id: category,
      label: LEVEL_LABELS[category],
      color: ACTIVITY_LEVEL[category],
      points: shown.map((row) => ({ x: row.x, y: daily ? row[category] / 60 : row[category] })),
    }));
  }, [state.data, view.start, view.end, view.resolution, daily]);
  const legend = [...series].reverse().map((line) => ({ id: line.id, label: line.label, color: line.color }));
  const format = daily ? (hours) => formatMinutes(hours * 60) : (minutes) => formatMinutes(minutes);
  return (
    <Card
      title="Activity level"
      note={daily ? "Hours a day at each level, stacked." : "Minutes an hour at each level, stacked."}
      explain="activityLevel"
      states={[state]}
      empty={!hasBuckets(state.data)}
      legend={legend}
      hidden={hidden}
      onToggle={toggle}
    >
      <StackedArea
        series={series}
        hidden={hidden}
        from={from}
        to={to}
        format={format}
        daily={daily}
        onDay={(x) => view.onDay(isoDate(x))}
      />
    </Card>
  );
}

/** Active Zone Minutes as a zone-by-day grid, darker for more minutes. */
function ZoneHeatmapCard({ state, view }) {
  const rows = useMemo(() => {
    if (!state.data) return [];
    const zones = presentCategories(state.data, AZM_ORDER).filter((zone) => AZM_ORDER.includes(zone));
    const totals = categoryDailyTotals(state.data, zones);
    const days = datesBetween(view.start, view.end);
    return zones.map((zone) => ({
      id: zone,
      label: AZM_LABELS[zone],
      data: days.map((day) => ({ x: day, y: totals[zone].get(day) ?? null })),
    }));
  }, [state.data, view.start, view.end]);
  return (
    <Card
      title="Active Zone Minutes"
      note="Minutes in each zone per day, darker for more. Google counts cardio and peak minutes double."
      explain="azm"
      states={[state]}
      empty={!hasBuckets(state.data)}
      height={40 + Math.max(rows.length, 1) * 40}
    >
      <DayHeatmap rows={rows} format={(minutes) => `${formatNumber(minutes)} min`} onDay={view.onDay} />
    </Card>
  );
}

/** Floors a day as a dot plot: a dot at the count, a stem down to zero. */
function FloorsCard({ state, view }) {
  const { from, to } = useBounds(view);
  const [hidden, toggle] = useHidden();
  const points = useMemo(
    () =>
      readingRows(state.data, "count", view.start, view.end)
        .filter((row) => row.value !== null)
        .map((row) => ({ x: row.x, y: row.value, day: row.day })),
    [state.data, view.start, view.end],
  );
  const axis = timeAxis(from, to);
  return (
    <Card
      title="Floors"
      explain="floors"
      states={[state]}
      empty={points.length === 0}
      legend={REFERENCE_KEYS}
      hidden={hidden}
      onToggle={toggle}
    >
      <Scatter
        points={points}
        color={CHART.floors}
        hidden={hidden}
        stems
        format={(value) => formatNumber(value)}
        xScale={{ type: "time", format: "native", precision: "day", min: from, max: to }}
        yScale={{ type: "linear", min: 0, max: "auto" }}
        axisBottom={{ tickValues: axis.tickValues, format: axis.format }}
        tooltip={(point) => (
          <div className="tip">
            <strong>{formatDay(point.x)}</strong>
            <div className="tip-row">
              <b>{formatNumber(point.y)}</b> floors
            </div>
          </div>
        )}
        onPoint={(point) => view.onDay(point.day)}
      />
    </Card>
  );
}

/** Hours a day sitting still, as a line: the trend matters more than any one day. */
function SedentaryCard({ state, view }) {
  const { from, to } = useBounds(view);
  const [hidden, toggle] = useHidden();
  const series = useMemo(() => {
    const byDate = new Map((state.data?.days ?? []).map((day) => [day.date, day.minutes]));
    const points = datesBetween(view.start, view.end).map((day) => ({
      x: parseIsoDate(day),
      y: byDate.has(day) ? byDate.get(day) / 60 : null,
    }));
    return [{ id: "sedentary", label: "Sitting still", color: CHART.sedentary, points }];
  }, [state.data, view.start, view.end]);
  return (
    <Card
      title="Sitting still"
      note="Hours a day in idle periods long enough for the watch to count. Lower is better."
      explain="sedentary"
      states={[state]}
      empty={!(state.data?.days ?? []).length}
      legend={REFERENCE_KEYS}
      hidden={hidden}
      onToggle={toggle}
    >
      <TimeLine
        series={series}
        hidden={hidden}
        from={from}
        to={to}
        unit=" h"
        digits={1}
        daily
        yFormat={(hours) => `${formatNumber(hours, 1)} h`}
        onDay={view.onDay}
      />
    </Card>
  );
}
