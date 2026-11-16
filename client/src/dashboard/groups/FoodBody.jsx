import { useMemo } from "react";

import Card from "../Card.jsx";
import { datesBetween, parseIsoDate, parseLocal } from "../dates.js";
import { formatNumber, formatTime, humanize } from "../format.js";
import { ROUTES } from "../routes.js";
import { CHART } from "../theme.js";
import { useData } from "../useData.js";
import { BarsCard, Figures, ReadingsCard } from "./common.jsx";
import { latestReading } from "./view.js";

const VO2_FIELDS = [{ field: "ml_per_kg_per_min", label: "VO₂ max", color: CHART.vo2 }];
const RUN_VO2_FIELDS = [{ field: "ml_per_kg_per_min", label: "Run VO₂ max", color: CHART.runVo2 }];

const kcalOf = (day) => day.kcal;
const litresOf = (day) => day.milliliters / 1000;

export default function FoodBody({ view }) {
  const routes = ROUTES.food(view);
  const nutrition = useData(...routes.nutrition);
  const hydration = useData(...routes.hydration);
  const height = useData(...routes.height);
  const vo2 = useData(...routes.vo2);
  const runVo2 = useData(...routes.runVo2);

  if (view.mode === "day") {
    const day = nutrition.data?.days?.[0];
    return (
      <>
        <Figures
          title="That day"
          explain="energy"
          states={[nutrition, hydration]}
          items={[
            { label: "Energy", value: day?.kcal ?? null, unit: "kcal" },
            ...Object.entries(day?.grams ?? {}).map(([name, grams]) => ({
              label: humanize(name),
              value: grams,
              unit: "g",
            })),
            {
              label: "Water",
              value: hydration.data?.days?.[0] ? hydration.data.days[0].milliliters / 1000 : null,
              unit: "L",
              digits: 2,
            },
          ]}
          emptyText="Nothing logged on this day."
        />
        <FoodLog state={nutrition} entries={day?.entries ?? []} />
      </>
    );
  }

  return (
    <>
      <DailyBars
        title="Energy eaten"
        explain="energy"
        state={nutrition}
        view={view}
        valueOf={kcalOf}
        color={CHART.energy}
        format={(value) => `${formatNumber(value)} kcal`}
        emptyText="No food logged in this range."
      />
      <DailyBars
        title="Water"
        explain="water"
        state={hydration}
        view={view}
        valueOf={litresOf}
        color={CHART.water}
        digits={2}
        unit=" L"
        format={(value) => `${formatNumber(value, 2)} L`}
        emptyText="No water logged in this range."
      />
      <ReadingsCard title="VO₂ max" note="ml/kg/min." explain="vo2" state={vo2} view={view} fields={VO2_FIELDS} digits={1} />
      <ReadingsCard
        title="Run VO₂ max"
        note="ml/kg/min, estimated from runs."
        explain="runVo2"
        state={runVo2}
        view={view}
        fields={RUN_VO2_FIELDS}
        digits={1}
      />
      <Figures
        title="Height"
        explain="height"
        states={[height]}
        items={[{ label: "Latest", value: latestReading(height.data, "meters"), unit: "m", digits: 2 }]}
        emptyText="No height recorded in this range."
      />
    </>
  );
}

function DailyBars({ title, explain, state, view, valueOf, color, format, unit, digits, emptyText }) {
  const rows = useMemo(() => {
    const byDate = new Map((state.data?.days ?? []).map((day) => [day.date, valueOf(day)]));
    return datesBetween(view.start, view.end).map((day) => ({
      key: day,
      day,
      x: parseIsoDate(day),
      value: byDate.get(day) ?? 0,
    }));
  }, [state.data, view.start, view.end, valueOf]);
  return (
    <BarsCard
      title={title}
      explain={explain}
      state={state}
      rows={rows}
      empty={!(state.data?.days ?? []).length}
      emptyText={emptyText}
      color={color}
      format={format}
      unit={unit}
      digits={digits}
      onDay={view.onDay}
    />
  );
}

function FoodLog({ state, entries }) {
  return (
    <Card title="Food log" states={[state]} empty={entries.length === 0} emptyText="No food logged." height="auto" wide>
      <div className="table-scroll">
        <table className="sessions">
          <thead>
            <tr>
              <th scope="col">Time</th>
              <th scope="col">Food</th>
              <th scope="col">Meal</th>
              <th scope="col" className="num">kcal</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry, index) => (
              <tr key={`${entry.time}-${index}`}>
                <td>{entry.time ? formatTime(parseLocal(entry.time)) : "–"}</td>
                <td>{entry.food ?? "–"}</td>
                <td>{entry.meal_type ? humanize(entry.meal_type) : "–"}</td>
                <td className="num">{formatNumber(entry.kcal)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
