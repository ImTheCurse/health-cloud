import { useMemo } from "react";

import Card from "../Card.jsx";
import { timeAxis } from "../charts/axis.js";
import Bars from "../charts/Bars.jsx";
import Scatter from "../charts/Scatter.jsx";
import { REFERENCE_KEYS } from "../charts/stats.js";
import { isoDate, parseIsoDate, parseLocal } from "../dates.js";
import { formatDay, formatLongDay, formatMinutes, formatNumber, formatPace } from "../format.js";
import { ROUTES } from "../routes.js";
import {
  EXERCISE_ZONES,
  paceMinutesPerKm,
  rollingMean,
  RUNNING,
  weeklyDistanceRows,
  weeklyZoneShareRows,
} from "../series.js";
import { CHART, INK, SEQUENTIAL, ZONE } from "../theme.js";
import { useData } from "../useData.js";
import { useHidden } from "../useHidden.js";
import { SessionLanes, SessionTable, SwarmCard } from "./Exercise.jsx";
import { useBounds } from "./view.js";

const ZONE_LABELS = { LIGHT: "Light", MODERATE: "Moderate", VIGOROUS: "Vigorous", PEAK: "Peak" };
const ZONE_KEYS = EXERCISE_ZONES.map((zone) => ({ key: zone, label: ZONE_LABELS[zone], color: ZONE[zone] }));

// Runs averaged into the pace trend line.
const TREND_WINDOW = 5;

/**
 * The running cards, drawn on the Exercise tab after the cards for every
 * session. Runs come from the same `/exercise` response.
 */
export default function Running({ view }) {
  const routes = ROUTES.exercise(view);
  const exercise = useData(...routes.exercise);
  const runs = useMemo(
    () => (exercise.data?.sessions ?? []).filter((session) => session.exercise_type === RUNNING),
    [exercise.data],
  );
  const colorOf = useMemo(() => () => CHART.runs, []);

  if (view.mode === "day") {
    return (
      <>
        <SessionLanes title="Runs across the day" state={exercise} sessions={runs} colorOf={colorOf} />
        <SessionTable title="Runs" state={exercise} sessions={runs} />
      </>
    );
  }

  return (
    <>
      <SwarmCard title="Runs" state={exercise} sessions={runs} colorOf={colorOf} view={view} />
      <PaceTrend state={exercise} runs={runs} view={view} />
      <WeeklyDistance state={exercise} runs={runs} view={view} />
      <AerobicEfficiency state={exercise} runs={runs} />
      <IntensitySplit state={exercise} runs={runs} view={view} />
    </>
  );
}

function runPoints(runs) {
  return runs
    .map((run) => ({ run, pace: paceMinutesPerKm(run), time: parseLocal(run.start) }))
    .filter((point) => point.pace && point.time)
    .sort((a, b) => a.time - b.time);
}

function RunTip({ run, pace }) {
  return (
    <div className="tip">
      <strong>{formatLongDay(parseLocal(run.start))}</strong>
      <div className="tip-row">
        <b>{formatPace(pace)} /km</b> · {formatNumber(run.distance_meters / 1000, 2)} km
      </div>
      {run.metrics?.average_heart_rate_bpm ? (
        <div className="tip-row">{run.metrics.average_heart_rate_bpm} bpm average</div>
      ) : null}
    </div>
  );
}

function PaceTrend({ state, runs, view }) {
  const { from, to } = useBounds(view);
  const [hidden, toggle] = useHidden();
  const points = useMemo(
    () => runPoints(runs).map(({ run, pace, time }) => ({ x: time, y: pace, run, pace })),
    [runs],
  );
  const trend = useMemo(() => rollingMean(points, TREND_WINDOW), [points]);
  const axis = timeAxis(from, to);
  return (
    <Card
      title="Pace"
      note={`Minutes per kilometre, faster lower down. The line is the mean of the last ${TREND_WINDOW} runs.`}
      explain="pace"
      states={[state]}
      empty={points.length === 0}
      legend={[
        { id: "trend", label: `Mean of last ${TREND_WINDOW}`, color: INK, shape: "line" },
        ...REFERENCE_KEYS,
      ]}
      hidden={hidden}
      onToggle={toggle}
    >
      <Scatter
        points={points}
        color={CHART.pace}
        line={hidden.has("trend") ? null : trend}
        hidden={hidden}
        format={formatPace}
        xScale={{ type: "time", format: "native", precision: "minute", min: from, max: to }}
        yScale={{ type: "linear", min: "auto", max: "auto" }}
        axisBottom={{ tickValues: axis.tickValues, format: axis.format }}
        axisLeft={{ format: formatPace }}
        tooltip={(point) => <RunTip run={point.run} pace={point.pace} />}
        onPoint={(point) => view.onDay(isoDate(point.x))}
      />
    </Card>
  );
}

function WeeklyDistance({ state, runs, view }) {
  const [hidden, toggle] = useHidden();
  const rows = useMemo(
    () => weeklyDistanceRows(runs, view.start, view.end),
    [runs, view.start, view.end],
  );
  const keys = useMemo(() => [{ key: "value", label: "Distance", color: CHART.weeklyDistance }], []);
  const layers = useMemo(() => (hidden.has("longest") ? [] : [LongestRunMarks(rows)]), [rows, hidden]);
  return (
    <Card
      title="Weekly distance"
      note="Kilometres run each week, Monday to Sunday. The dark tick is the week's longest run."
      explain="weeklyDistance"
      states={[state]}
      empty={runs.length === 0}
      legend={[{ id: "longest", label: "Longest run", color: INK, shape: "line" }, ...REFERENCE_KEYS]}
      hidden={hidden}
      onToggle={toggle}
    >
      <Bars
        rows={rows}
        keys={keys}
        hidden={hidden}
        daily
        digits={1}
        unit=" km"
        layers={layers}
        format={(value, row) =>
          `${formatNumber(value, 1)} km, week of ${formatDay(row.x)} · longest ${formatNumber(row.longest, 1)} km`
        }
      />
    </Card>
  );
}

function LongestRunMarks(rows) {
  const longestByKey = new Map(rows.map((row) => [row.key, row.longest]));
  return function Marks({ bars, yScale }) {
    return (
      <g pointerEvents="none">
        {bars
          .filter((bar) => longestByKey.get(bar.data.indexValue) > 0)
          .map((bar) => {
            const y = yScale(longestByKey.get(bar.data.indexValue));
            return (
              <line
                key={bar.key}
                x1={bar.x + bar.width * 0.15}
                x2={bar.x + bar.width * 0.85}
                y1={y}
                y2={y}
                stroke={INK}
                strokeWidth={2.5}
              />
            );
          })}
      </g>
    );
  };
}

function AerobicEfficiency({ state, runs }) {
  const points = useMemo(() => {
    const list = runPoints(runs).filter(({ run }) => run.metrics?.average_heart_rate_bpm);
    const first = list[0]?.time.getTime() ?? 0;
    const span = (list.at(-1)?.time.getTime() ?? 0) - first || 1;
    // Older runs light, newer dark: the drift over time is the point.
    const steps = SEQUENTIAL.slice(2);
    return list.map(({ run, pace, time }) => ({
      x: pace,
      y: run.metrics.average_heart_rate_bpm,
      color: steps[Math.min(steps.length - 1, Math.floor(((time - first) / span) * steps.length))],
      run,
      pace,
    }));
  }, [runs]);
  return (
    <Card
      title="Aerobic efficiency"
      note="Pace against average heart rate per run, older runs lighter. Getting fitter moves dots right (faster) at the same height."
      explain="efficiency"
      states={[state]}
      empty={points.length === 0}
      legend={[
        { id: "older", label: "Older", color: SEQUENTIAL[2], shape: "dot" },
        { id: "newer", label: "Newer", color: SEQUENTIAL.at(-1), shape: "dot" },
      ]}
    >
      <Scatter
        points={points}
        xScale={{ type: "linear", min: "auto", max: "auto", reverse: true }}
        yScale={{ type: "linear", min: "auto", max: "auto" }}
        axisBottom={{ format: formatPace, legend: "pace, min/km (faster →)", legendOffset: 32, legendPosition: "middle" }}
        axisLeft={{ format: (bpm) => `${bpm}` }}
        tooltip={(point) => <RunTip run={point.run} pace={point.pace} />}
      />
    </Card>
  );
}

function IntensitySplit({ state, runs, view }) {
  const [hidden, toggle] = useHidden();
  const rows = useMemo(
    () => weeklyZoneShareRows(runs, view.start, view.end),
    [runs, view.start, view.end],
  );
  return (
    <Card
      title="Intensity by week"
      note="Share of each week's running time in each heart-rate zone. A common target keeps about 80% easy."
      explain="intensity"
      states={[state]}
      empty={rows.every((row) => row.totalMinutes === 0)}
      legend={ZONE_KEYS.map((k) => ({ id: k.key, label: k.label, color: k.color }))}
      hidden={hidden}
      onToggle={toggle}
    >
      <Bars
        rows={rows}
        keys={ZONE_KEYS}
        hidden={hidden}
        references={false}
        daily
        minValue={0}
        maxValue={100}
        yFormat={(value) => `${value}%`}
        format={(value, row) =>
          `${formatNumber(value)}% of ${formatMinutes(row.totalMinutes)}, week of ${formatDay(parseIsoDate(row.day))}`
        }
      />
    </Card>
  );
}
