import { useMemo } from "react";

import Card from "../Card.jsx";
import ExerciseSwarm from "../charts/ExerciseSwarm.jsx";
import Lanes from "../charts/Lanes.jsx";
import { parseLocal } from "../dates.js";
import { formatDayTime, formatMinutes, formatNumber, humanize } from "../format.js";
import { exerciseMinuteRows, periodSpans, sessionLoad } from "../series.js";
import { ROUTES } from "../routes.js";
import { CHART } from "../theme.js";
import { useData } from "../useData.js";
import { BarsCard } from "./common.jsx";
import Running from "./Running.jsx";
import { useTypeColors } from "./view.js";

export default function Exercise({ view }) {
  const routes = ROUTES.exercise(view);
  const exercise = useData(...routes.exercise);
  const sessions = useMemo(() => exercise.data?.sessions ?? [], [exercise.data]);
  const { colorOf, legend } = useTypeColors(sessions);

  if (view.mode === "day") {
    return (
      <>
        <SessionLanes title="Sessions across the day" state={exercise} sessions={sessions} colorOf={colorOf} />
        <SessionTable title="Sessions" state={exercise} sessions={sessions} />
        <Running view={view} />
      </>
    );
  }

  return (
    <>
      <SwarmCard
        title="Sessions"
        state={exercise}
        sessions={sessions}
        colorOf={colorOf}
        legend={legend}
        view={view}
      />
      <MinutesCard state={exercise} sessions={sessions} view={view} />
      <Running view={view} />
      <SessionTable title="Latest sessions" state={exercise} sessions={sessions} limit={12} />
    </>
  );
}

export function SwarmCard({ title, state, sessions, colorOf, legend, view }) {
  return (
    <Card
      title={title}
      note="One dot per session; a bigger dot was a harder session. Dotted lines mark midnight."
      explain="exercise"
      states={[state]}
      empty={sessions.length === 0}
      legend={legend}
      height={220}
      wide
    >
      <ExerciseSwarm
        sessions={sessions}
        colorOf={colorOf}
        start={view.start}
        end={view.end}
        onDay={view.onDay}
      />
    </Card>
  );
}

function MinutesCard({ state, sessions, view }) {
  const rows = useMemo(
    () => exerciseMinuteRows(sessions, view.start, view.end),
    [sessions, view.start, view.end],
  );
  return (
    <BarsCard
      title="Minutes of exercise"
      explain="exerciseMinutes"
      state={state}
      rows={rows}
      empty={sessions.length === 0}
      color={CHART.exerciseMinutes}
      format={formatMinutes}
      unit=" min"
      onDay={view.onDay}
    />
  );
}

function sessionDetail(session) {
  const parts = [formatMinutes(session.duration_minutes)];
  if (session.distance_meters) parts.push(`${formatNumber(session.distance_meters / 1000, 2)} km`);
  if (session.metrics?.average_heart_rate_bpm) parts.push(`${session.metrics.average_heart_rate_bpm} bpm`);
  return parts.join(" · ");
}

/** One lane per exercise type across the day, like the idle-period chart. */
export function SessionLanes({ title, state, sessions, colorOf }) {
  const lanes = useMemo(() => {
    const byType = new Map();
    for (const session of sessions) {
      const type = session.exercise_type ?? "OTHER";
      if (!byType.has(type)) byType.set(type, []);
      byType.get(type).push(session);
    }
    return [...byType.entries()].map(([type, list]) => ({
      id: type,
      label: humanize(type),
      color: colorOf(type),
      spans: periodSpans(list, sessionDetail),
    }));
  }, [sessions, colorOf]);
  return (
    <Card
      title={title}
      note="Hover a block for the session."
      explain="exerciseTimeline"
      states={[state]}
      empty={sessions.length === 0}
      emptyText="No sessions on this day."
      height="auto"
      wide
    >
      <Lanes lanes={lanes} label={title} />
    </Card>
  );
}

export function SessionTable({ title, state, sessions, limit }) {
  const shown = useMemo(() => {
    const newest = [...sessions].sort((a, b) => ((a.start ?? "") < (b.start ?? "") ? 1 : -1));
    return limit ? newest.slice(0, limit) : newest;
  }, [sessions, limit]);
  return (
    <Card
      title={title}
      states={[state]}
      empty={sessions.length === 0}
      emptyText="No sessions recorded."
      height="auto"
      wide
    >
      <div className="table-scroll">
        <table className="sessions">
          <thead>
            <tr>
              <th scope="col">When</th>
              <th scope="col">Session</th>
              <th scope="col" className="num">Time</th>
              <th scope="col" className="num">Distance</th>
              <th scope="col" className="num">Avg HR</th>
              <th scope="col" className="num">Load</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((session, index) => (
              <tr key={`${session.start}-${index}`}>
                <td>{session.start ? formatDayTime(parseLocal(session.start)) : session.date}</td>
                <td>{session.name ?? humanize(session.exercise_type)}</td>
                <td className="num">{formatMinutes(session.duration_minutes)}</td>
                <td className="num">
                  {session.distance_meters ? `${formatNumber(session.distance_meters / 1000, 2)} km` : "–"}
                </td>
                <td className="num">{session.metrics?.average_heart_rate_bpm ?? "–"}</td>
                <td className="num">{formatNumber(sessionLoad(session).value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
