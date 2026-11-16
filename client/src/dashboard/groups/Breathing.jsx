import { ROUTES } from "../routes.js";
import { CHART } from "../theme.js";
import { useData } from "../useData.js";
import { Figures, ReadingBandCard, ReadingsCard, StatCard } from "./common.jsx";
import { latestReading } from "./view.js";

const SPO2_BAND = {
  low: "lower_bound_percent",
  mid: "average_percent",
  high: "upper_bound_percent",
};
const SPO2_LABELS = { low: "Lower bound", mid: "Nightly average", high: "Upper bound" };
const BREATHING_FIELDS = [{ field: "breaths_per_minute", label: "Breathing rate", color: CHART.breathing }];

export default function Breathing({ view }) {
  const routes = ROUTES.breathing(view);
  const oxygen = useData(...routes.oxygen);
  const oxygenDaily = useData(...routes.oxygenDaily);
  const breathing = useData(...routes.breathing);

  if (view.mode === "day") {
    return (
      <>
        <StatCard title="Blood oxygen" explain="oxygen" state={oxygen} view={view} unit="%" digits={1} color={CHART.oxygen} />
        <Figures
          title="That night"
          explain="oxygenNightly"
          states={[oxygenDaily, breathing]}
          items={[
            { label: "Average SpO₂", value: latestReading(oxygenDaily.data, "average_percent"), unit: "%", digits: 1 },
            {
              label: "Variation",
              value: latestReading(oxygenDaily.data, "standard_deviation_percent"),
              unit: "% sd",
              digits: 1,
            },
            {
              label: "Breathing rate",
              value: latestReading(breathing.data, "breaths_per_minute"),
              unit: "breaths/min",
              digits: 1,
            },
          ]}
        />
      </>
    );
  }

  return (
    <>
      <StatCard
        title="Blood oxygen"
        note="SpO₂ samples, mostly taken in sleep."
        explain="oxygen"
        state={oxygen}
        view={view}
        unit="%"
        digits={1}
        color={CHART.oxygen}
      />
      <ReadingBandCard
        title="Nightly blood oxygen"
        note="Google's nightly average; hover for its lower and upper bound."
        explain="oxygenNightly"
        state={oxygenDaily}
        view={view}
        fields={SPO2_BAND}
        labels={SPO2_LABELS}
        unit="%"
        digits={1}
        color={CHART.oxygenNightly}
      />
      <ReadingsCard
        title="Breathing rate"
        note="Breaths per minute, one figure a day."
        explain="breathing"
        state={breathing}
        view={view}
        fields={BREATHING_FIELDS}
        digits={1}
      />
    </>
  );
}
