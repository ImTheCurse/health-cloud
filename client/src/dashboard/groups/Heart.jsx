import { useMemo } from "react";

import { formatNumber, humanize } from "../format.js";
import { ROUTES } from "../routes.js";
import { CHART, ZONE } from "../theme.js";
import { useData } from "../useData.js";
import { CategoryCard, Figures, HeatmapCard, ReadingsCard, StatCard } from "./common.jsx";
import { latestReading } from "./view.js";

const ZONE_ORDER = ["LIGHT", "MODERATE", "VIGOROUS", "PEAK"];
const ZONE_LABELS = { LIGHT: "Light", MODERATE: "Moderate", VIGOROUS: "Vigorous", PEAK: "Peak" };

const HRV_FIELDS = [
  { field: "average_ms", label: "Night average", color: CHART.nightlyHrv },
  { field: "deep_sleep_rmssd_ms", label: "Deep sleep", color: CHART.deepSleepHrv },
];
const NON_REM_FIELDS = [{ field: "non_rem_heart_rate_bpm", label: "Non-REM heart rate", color: CHART.nonRemHeartRate }];
const ENTROPY_FIELDS = [{ field: "entropy", label: "Entropy", color: CHART.entropy }];
const RESTING_FIELDS = [{ field: "bpm", label: "Resting heart rate", color: CHART.resting }];

const averageOf = (bucket) => bucket.avg;
const formatBpm = (value) => `${formatNumber(value, 0)} bpm average`;

export default function Heart({ view }) {
  const routes = ROUTES.heart(view);
  const heartRate = useData(...routes.heartRate);
  const resting = useData(...routes.resting);
  const zones = useData(...routes.zones);
  const timeInZone = useData(...routes.timeInZone);
  const variability = useData(...routes.variability);
  const variabilityDaily = useData(...routes.variabilityDaily);

  const zoneLimits = useMemo(() => zones.data?.days?.at(-1)?.zones ?? [], [zones.data]);
  const zoneBands = useMemo(
    () =>
      zoneLimits
        .filter((zone) => zone.min_bpm !== null && zone.max_bpm !== null)
        .map((zone) => ({
          from: zone.min_bpm,
          to: zone.max_bpm,
          label: humanize(zone.zone),
          color: ZONE[zone.zone] ?? CHART.entropy,
        })),
    [zoneLimits],
  );

  const zoneCard = (
    <CategoryCard
      title="Time in heart-rate zone"
      explain="timeInZone"
      state={timeInZone}
      view={view}
      order={ZONE_ORDER}
      labels={ZONE_LABELS}
      colors={ZONE}
    />
  );
  const variabilityCard = (
    <StatCard
      title="Heart-rate variability"
      explain="variability"
      state={variability}
      view={view}
      unit=" ms"
      digits={1}
      color={CHART.variability}
    />
  );

  if (view.mode === "day") {
    return (
      <>
        <StatCard
          title="Heart rate"
          note="Shaded behind it: your heart-rate zones that day."
          explain="heartRate"
          state={heartRate}
          view={view}
          unit=" bpm"
          bands={zoneBands}
          color={CHART.heartRate}
          wide
        />
        {zoneCard}
        <Figures
          title="That day"
          states={[resting, variabilityDaily]}
          items={[
            { label: "Resting heart rate", value: latestReading(resting.data, "bpm"), unit: "bpm" },
            { label: "Nightly HRV", value: latestReading(variabilityDaily.data, "average_ms"), unit: "ms", digits: 1 },
            {
              label: "Non-REM heart rate",
              value: latestReading(variabilityDaily.data, "non_rem_heart_rate_bpm"),
              unit: "bpm",
            },
          ]}
        />
        {variabilityCard}
      </>
    );
  }

  return (
    <>
      <StatCard title="Heart rate" explain="heartRate" state={heartRate} view={view} unit=" bpm" color={CHART.heartRate} wide />
      {view.resolution === "1h" && (
        <HeatmapCard
          title="Heart rate by hour"
          note="Average per hour; darker is higher. Click a row to open that day."
          explain="heartRate"
          state={heartRate}
          view={view}
          pick={averageOf}
          format={formatBpm}
        />
      )}
      <ReadingsCard
        title="Resting heart rate"
        explain="resting"
        state={resting}
        view={view}
        fields={RESTING_FIELDS}
        unit=" bpm"
      />
      {zoneCard}
      {variabilityCard}
      <ReadingsCard
        title="Nightly heart-rate variability"
        note="RMSSD, over the night and in deep sleep."
        explain="nightlyHrv"
        state={variabilityDaily}
        view={view}
        fields={HRV_FIELDS}
        unit=" ms"
        digits={1}
      />
      <ReadingsCard
        title="Non-REM heart rate"
        explain="nonRemHeartRate"
        state={variabilityDaily}
        view={view}
        fields={NON_REM_FIELDS}
        unit=" bpm"
      />
      <ReadingsCard title="HRV entropy" explain="entropy" state={variabilityDaily} view={view} fields={ENTROPY_FIELDS} digits={2} />
      <Figures
        title="Heart-rate zones"
        note="The latest limits Google set for you."
        explain="zones"
        states={[zones]}
        emptyText="No zone limits in this range."
        items={zoneLimits.map((zone) => ({
          label: humanize(zone.zone),
          value: `${zone.min_bpm ?? "…"}–${zone.max_bpm ?? "…"}`,
          unit: "bpm",
        }))}
      />
    </>
  );
}
