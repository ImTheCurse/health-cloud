import { useMemo } from "react";

import Card from "../Card.jsx";
import Lanes from "../charts/Lanes.jsx";
import StepsCalendar from "../charts/StepsCalendar.jsx";
import { datesBetween, parseIsoDate } from "../dates.js";
import { formatMinutes, formatNumber } from "../format.js";
import { hasBuckets, periodSpans, readingRows, sumRows } from "../series.js";
import { ROUTES } from "../routes.js";
import { ACTIVITY_LEVEL, AZM_ZONE, CHART } from "../theme.js";
import { useData } from "../useData.js";
import { BarsCard, CategoryCard, Figures, HeatmapCard, SumCard } from "./common.jsx";

const LEVEL_ORDER = ["SEDENTARY", "LIGHTLY_ACTIVE", "MODERATELY_ACTIVE", "VERY_ACTIVE"];
const LEVEL_LABELS = {
  SEDENTARY: "Sedentary",
  LIGHTLY_ACTIVE: "Light",
  MODERATELY_ACTIVE: "Moderate",
  VERY_ACTIVE: "Very active",
};
const AZM_ORDER = ["FAT_BURN", "CARDIO", "PEAK"];
const AZM_LABELS = { FAT_BURN: "Fat burn", CARDIO: "Cardio", PEAK: "Peak" };

const totalOf = (bucket) => bucket.total;
const formatSteps = (value) => `${formatNumber(value)} steps`;
const formatKm = (value) => `${formatNumber(value, 2)} km`;

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

  const levelCard = (
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
  const zoneCard = (
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
  const stepsCard = (
    <SumCard
      title="Steps"
      note={view.mode === "day" ? `${formatNumber(stepTotal)} in total.` : undefined}
      explain="steps"
      state={steps}
      view={view}
      format={formatSteps}
      color={CHART.steps}
    />
  );
  const distanceCard = (
    <SumCard
      title="Distance"
      explain="distance"
      state={distance}
      view={view}
      scale={1 / 1000}
      digits={1}
      unit=" km"
      format={formatKm}
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

function FloorsCard({ state, view }) {
  const rows = useMemo(
    () => readingRows(state.data, "count", view.start, view.end).map((row) => ({ ...row, value: row.value ?? 0 })),
    [state.data, view.start, view.end],
  );
  return (
    <BarsCard
      title="Floors"
      explain="floors"
      state={state}
      rows={rows}
      color={CHART.floors}
      unit=" floors"
      onDay={view.onDay}
    />
  );
}

function SedentaryCard({ state, view }) {
  const rows = useMemo(() => {
    const byDate = new Map((state.data?.days ?? []).map((day) => [day.date, day.minutes]));
    return datesBetween(view.start, view.end).map((day) => ({
      key: day,
      day,
      x: parseIsoDate(day),
      value: (byDate.get(day) ?? 0) / 60,
    }));
  }, [state.data, view.start, view.end]);
  return (
    <BarsCard
      title="Sitting still"
      note="Hours a day in idle periods long enough for the watch to count."
      explain="sedentary"
      state={state}
      rows={rows}
      color={CHART.sedentary}
      format={(hours) => formatMinutes(hours * 60)}
      yFormat={(hours) => `${hours} h`}
      digits={1}
      unit=" h"
      onDay={view.onDay}
    />
  );
}
