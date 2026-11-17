import { ResponsiveSwarmPlot } from "@nivo/swarmplot";
import { useMemo } from "react";

import { addDays, datesBetween, parseIsoDate, parseLocal } from "../dates.js";
import { formatDayTime, formatMinutes, formatNumber, humanize } from "../format.js";
import { sessionLoad } from "../series.js";
import { INK_SOFT, nivoTheme } from "../theme.js";
import { timeAxis } from "./axis.js";

// Node diameters. Area, not radius, grows with load -- radius grows with its
// square root -- and the cap keeps one hard session from covering its week.
const MIN_SIZE = 7;
const MAX_SIZE = 26;

/**
 * One node per session along time; bigger is harder, colour is the type.
 * Sessions on the same day push apart instead of overlapping.
 */
export default function ExerciseSwarm({ sessions, colorOf, start, end, onDay }) {
  const from = useMemo(() => parseIsoDate(start), [start]);
  const to = useMemo(() => parseIsoDate(end), [end]);

  const data = useMemo(() => {
    const loads = sessions.map((session) => sessionLoad(session));
    const maxLoad = Math.max(1, ...loads.map((load) => load.value));
    return sessions
      .map((session, index) => ({
        id: `${session.start ?? session.date}-${index}`,
        group: "all",
        time: parseLocal(session.start) ?? parseIsoDate(session.date),
        diameter: MIN_SIZE + (MAX_SIZE - MIN_SIZE) * Math.sqrt(loads[index].value / maxLoad),
        load: loads[index],
        session,
      }))
      .filter((node) => node.time >= from && node.time < to);
  }, [sessions, from, to]);

  const axis = timeAxis(from, to);
  const layers = useMemo(() => ["grid", DayLines(start, end), "axes", "circles", "mesh"], [start, end]);

  return (
    <ResponsiveSwarmPlot
      data={data}
      groups={["all"]}
      groupBy="group"
      id="id"
      value="time"
      valueScale={{ type: "time", format: "native", precision: "minute", min: from, max: to }}
      size={(node) => node.diameter}
      spacing={1}
      gap={0}
      forceStrength={6}
      simulationIterations={160}
      layout="horizontal"
      theme={nivoTheme}
      margin={{ top: 16, right: 16, bottom: 30, left: 16 }}
      colors={(node) => colorOf(node.data.session.exercise_type)}
      borderWidth={1.5}
      borderColor="#ffffff"
      enableGridX={false}
      enableGridY={false}
      axisLeft={null}
      axisRight={null}
      axisTop={null}
      axisBottom={{ tickSize: 4, tickPadding: 4, tickValues: axis.tickValues, format: axis.format }}
      layers={layers}
      tooltip={(node) => <SessionTip session={node.data.session} load={node.data.load} />}
      onClick={(node) => onDay?.(node.data.session.date)}
      animate={false}
      role="img"
    />
  );
}

function SessionTip({ session, load }) {
  return (
    <div className="tip">
      <strong>
        {session.name ?? humanize(session.exercise_type)}
        {session.start ? `, ${formatDayTime(parseLocal(session.start))}` : ""}
      </strong>
      <div className="tip-row">{formatMinutes(session.duration_minutes)}</div>
      {session.distance_meters ? (
        <div className="tip-row">{formatNumber(session.distance_meters / 1000, 2)} km</div>
      ) : null}
      {session.metrics?.average_heart_rate_bpm ? (
        <div className="tip-row">{session.metrics.average_heart_rate_bpm} bpm average</div>
      ) : null}
      <div className="tip-row muted">
        Load {formatNumber(load.value)} ({load.source})
      </div>
    </div>
  );
}

/**
 * Dotted lines at midnight, so it is clear which day a session belongs to.
 * Past a month, only Mondays get one, or the lines would crowd the sessions.
 */
function DayLines(start, end) {
  const days = datesBetween(start, addDays(end, 1));
  const weekly = days.length > 32;
  const marks = days.filter((day) => !weekly || parseIsoDate(day).getDay() === 1);
  return function Lines({ xScale, innerHeight }) {
    return (
      <g pointerEvents="none">
        {marks.map((day) => {
          const x = xScale(parseIsoDate(day));
          return (
            <line
              key={day}
              x1={x}
              x2={x}
              y1={0}
              y2={innerHeight}
              stroke={INK_SOFT}
              strokeOpacity={0.45}
              strokeDasharray="2 4"
            />
          );
        })}
      </g>
    );
  };
}
