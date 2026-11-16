import { useMemo } from "react";

import Card from "../Card.jsx";
import Bars from "../charts/Bars.jsx";
import { REFERENCE_KEYS } from "../charts/stats.js";
import TimeLine from "../charts/TimeLine.jsx";
import { parseLocal } from "../dates.js";
import { formatClockHours, formatMinutes, formatNumber, formatTime } from "../format.js";
import {
  allEmpty,
  hypnogramPoints,
  noonHoursToClock,
  readingRows,
  SLEEP_STAGES,
  sleepStageRows,
  sleepTimingRows,
  STAGE_BY_LEVEL,
} from "../series.js";
import { ROUTES } from "../routes.js";
import { ABOVE, BELOW, CHART, FELL_ASLEEP, STAGE, WOKE_UP } from "../theme.js";
import { useData } from "../useData.js";
import { useHidden } from "../useHidden.js";
import { Figures, ReadingsCard } from "./common.jsx";
import { latestReading } from "./view.js";

const STAGE_LABELS = { DEEP: "Deep", LIGHT: "Light", REM: "REM", AWAKE: "Awake" };
const STAGE_KEYS = SLEEP_STAGES.map((stage) => ({ key: stage, label: STAGE_LABELS[stage], color: STAGE[stage] }));
// Step-line levels, bottom to top, as `hypnogramPoints` numbers them.
const LEVEL_COLORS = [STAGE.DEEP, STAGE.LIGHT, STAGE.REM, STAGE.AWAKE];

const BREATHING_FIELDS = [
  { field: "full_sleep", label: "Whole night", color: CHART.breathingNight },
  { field: "deep_sleep", label: "Deep", color: STAGE.DEEP },
  { field: "light_sleep", label: "Light", color: STAGE.LIGHT },
  { field: "rem_sleep", label: "REM", color: STAGE.REM },
];

export default function Sleep({ view }) {
  const routes = ROUTES.sleep(view);
  const sleep = useData(...routes.sleep);
  const temperature = useData(...routes.temperature);
  const breathing = useData(...routes.breathing);

  if (view.mode === "day") {
    const sessions = sleep.data?.days?.flatMap((day) => day.sessions) ?? [];
    return (
      <>
        {sessions.length === 0 && (
          <Card title="Sleep stages" explain="sleepStages" states={[sleep]} empty emptyText="No sleep ended on this day." />
        )}
        {sessions.map((session) => (
          <Hypnogram key={session.start} session={session} state={sleep} />
        ))}
        {sessions.map((session) => (
          <Figures
            key={`figures-${session.start}`}
            title={session.main_sleep ? "The night" : "Nap"}
            explain="sleep"
            states={[sleep]}
            items={[
              { label: "Asleep", value: formatMinutes(session.minutes_asleep) },
              { label: "Awake", value: formatMinutes(session.minutes_awake) },
              { label: "To fall asleep", value: formatMinutes(session.minutes_to_fall_asleep) },
              ...STAGE_KEYS.filter((stage) => stage.key !== "AWAKE").map((stage) => ({
                label: stage.label,
                value: formatMinutes(session.stage_minutes[stage.key]),
              })),
            ]}
          />
        ))}
        <Figures
          title="Breathing and temperature"
          explain="breathingNight"
          states={[breathing, temperature]}
          items={[
            { label: "Breathing", value: latestReading(breathing.data, "full_sleep"), unit: "breaths/min", digits: 1 },
            { label: "Skin temperature", value: latestReading(temperature.data, "nightly_celsius"), unit: "°C", digits: 2 },
            { label: "Baseline", value: latestReading(temperature.data, "baseline_celsius"), unit: "°C", digits: 2 },
          ]}
        />
      </>
    );
  }

  return (
    <>
      <SleepStages state={sleep} view={view} />
      <SleepTiming state={sleep} view={view} />
      <TemperatureDeviation state={temperature} view={view} />
      <ReadingsCard
        title="Breathing rate in sleep"
        note="Breaths per minute, over the night and in each stage."
        explain="breathingNight"
        state={breathing}
        view={view}
        fields={BREATHING_FIELDS}
        digits={1}
      />
    </>
  );
}

function SleepStages({ state, view }) {
  const [hidden, toggle] = useHidden();
  const rows = useMemo(
    () => sleepStageRows(state.data, view.start, view.end),
    [state.data, view.start, view.end],
  );
  return (
    <Card
      title="Sleep"
      note="Hours per night by stage, naps included, on the day the sleep ended."
      explain="sleep"
      states={[state]}
      empty={allEmpty(rows, SLEEP_STAGES)}
      legend={[...STAGE_KEYS.map((k) => ({ id: k.key, label: k.label, color: k.color })), ...REFERENCE_KEYS]}
      hidden={hidden}
      onToggle={toggle}
    >
      <Bars
        rows={rows}
        keys={STAGE_KEYS}
        hidden={hidden}
        daily
        format={(hours) => formatMinutes(hours * 60)}
        yFormat={(hours) => `${hours} h`}
        onDay={view.onDay}
      />
    </Card>
  );
}

const TIMING_KEYS = [
  { key: "lead", label: "", color: "transparent" },
  { key: "asleep", label: "Asleep", color: CHART.sleepTiming },
];

function SleepTiming({ state, view }) {
  const { rows, base, top } = useMemo(
    () => sleepTimingRows(state.data, view.start, view.end),
    [state.data, view.start, view.end],
  );
  const clock = (offset) => formatClockHours(noonHoursToClock(offset + base));
  const ticks = [];
  for (let hour = 0; hour <= top; hour += top > 10 ? 2 : 1) ticks.push(hour);
  const layers = useMemo(() => [SleepMarkers(rows)], [rows]);

  return (
    <Card
      title="Sleep timing"
      note="Main sleep each night. Even bars mean a steady schedule."
      explain="sleepTiming"
      states={[state]}
      empty={rows.every((row) => row.asleep === 0)}
      legend={[
        { id: "fell", label: "Fell asleep", color: FELL_ASLEEP, shape: "dot" },
        { id: "woke", label: "Woke up", color: WOKE_UP, shape: "dot" },
      ]}
    >
      <Bars
        rows={rows}
        keys={TIMING_KEYS}
        spacers={["lead"]}
        minValue={0}
        maxValue={top}
        reverse
        references={false}
        yTicks={ticks}
        yFormat={clock}
        daily
        layers={layers}
        format={(_, row) => `${clock(row.lead)} to ${clock(row.lead + row.asleep)}`}
        onDay={view.onDay}
      />
    </Card>
  );
}

/** A dot where each night's sleep starts and another where it ends. */
function SleepMarkers(rows) {
  const byKey = new Map(rows.map((row) => [row.key, row]));
  return function Markers({ bars, yScale }) {
    return (
      <g pointerEvents="none">
        {bars
          .filter((bar) => bar.data.id === "asleep" && byKey.get(bar.data.indexValue)?.asleep)
          .map((bar) => {
            const row = byKey.get(bar.data.indexValue);
            const x = bar.x + bar.width / 2;
            const r = Math.max(3, Math.min(6, bar.width / 2.5));
            return (
              <g key={bar.key}>
                <circle cx={x} cy={yScale(row.lead)} r={r} fill={FELL_ASLEEP} stroke="#ffffff" strokeWidth={1.5} />
                <circle cx={x} cy={yScale(row.lead + row.asleep)} r={r} fill={WOKE_UP} stroke="#ffffff" strokeWidth={1.5} />
              </g>
            );
          })}
      </g>
    );
  };
}

function TemperatureDeviation({ state, view }) {
  const rows = useMemo(() => {
    const nightly = readingRows(state.data, "nightly_celsius", view.start, view.end);
    const baseline = readingRows(state.data, "baseline_celsius", view.start, view.end);
    return nightly.map((row, index) => ({
      ...row,
      value:
        row.value === null || baseline[index].value === null
          ? 0
          : Math.round((row.value - baseline[index].value) * 100) / 100,
    }));
  }, [state.data, view.start, view.end]);

  const format = (value) => `${value > 0 ? "+" : ""}${formatNumber(value, 2)} °C`;
  // Symmetric around zero, so above and below the baseline read at one scale.
  const reach = Math.max(0.1, ...rows.map((row) => Math.abs(row.value)));
  const limit = Math.ceil(reach * 10) / 10;
  return (
    <Card
      title="Skin temperature"
      note="Each night against your baseline: red above it, blue below."
      explain="temperature"
      states={[state]}
      empty={rows.every((row) => row.value === 0)}
      legend={[
        { id: "above", label: "Above baseline", color: ABOVE },
        { id: "below", label: "Below baseline", color: BELOW },
      ]}
    >
      <Bars
        rows={rows}
        keys={[{ key: "value", label: "Difference", color: ABOVE }]}
        colorFor={(bar) => (bar.value >= 0 ? ABOVE : BELOW)}
        references={false}
        minValue={-limit}
        maxValue={limit}
        daily
        format={format}
        yFormat={(value) => `${value > 0 ? "+" : ""}${value}`}
        onDay={view.onDay}
      />
    </Card>
  );
}

function Hypnogram({ session, state }) {
  const from = parseLocal(session.start);
  const to = parseLocal(session.end);
  const series = useMemo(
    () => [{ id: "stage", label: "Stage", color: STAGE.LIGHT, points: hypnogramPoints(session) }],
    [session],
  );
  return (
    <Card
      title={session.main_sleep ? "Sleep stages" : "Nap stages"}
      note={`${formatTime(from)} to ${formatTime(to)}`}
      explain="sleepStages"
      states={[state]}
      legend={STAGE_KEYS.map((k) => ({ id: k.key, label: k.label, color: k.color }))}
      wide
    >
      <TimeLine
        series={series}
        from={from}
        to={to}
        curve="stepAfter"
        stepColors={LEVEL_COLORS}
        references={false}
        yMin={0}
        yMax={3}
        yTicks={[0, 1, 2, 3]}
        yFormat={(level) => STAGE_BY_LEVEL[level] ?? ""}
      />
    </Card>
  );
}
