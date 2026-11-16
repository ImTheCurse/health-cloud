// Cards shared by the tabs: one per API response shape, so a tab only says
// which route goes where. Every chart card has legend toggles for its series
// and for the dashed average, max and min lines, and a "Learn more" dialog.

import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import { useMemo, useState } from "react";

import Card from "../Card.jsx";
import { heatmapHeight } from "../charts/axis.js";
import Bars from "../charts/Bars.jsx";
import HourHeatmap from "../charts/HourHeatmap.jsx";
import Lanes from "../charts/Lanes.jsx";
import { REFERENCE_KEYS } from "../charts/stats.js";
import TimeLine from "../charts/TimeLine.jsx";
import { datesBetween } from "../dates.js";
import { PERSONAL } from "../explain.js";
import { formatMinutes, formatNumber } from "../format.js";
import {
  categoryLanes,
  categoryRows,
  hasBuckets,
  hasReadings,
  hourByDay,
  presentCategories,
  readingBandRows,
  readingSeries,
  dailyReadingValues,
  dailyStatValues,
  personalRanges,
  statRows,
  sumRows,
} from "../series.js";
import { PERSONAL_SWATCH } from "../theme.js";
import { useHidden } from "../useHidden.js";
import { useBounds } from "./view.js";

/**
 * Legend entries: the series when there are several, the personal range when
 * there is one, then the reference lines.
 */
function legendOf(series, personal) {
  const entries = series.length > 1 ? series.map((s) => ({ id: s.id, label: s.label, color: s.color, shape: s.shape ?? "line" })) : [];
  if (personal?.ranges.size) entries.push({ id: "personal", label: "Personal range", color: PERSONAL_SWATCH });
  return [...entries, ...REFERENCE_KEYS];
}

/**
 * Your usual range per visible day, from the 30 days of `history` before the
 * view and the view itself, or null where the chart has none. `values` turns
 * the payloads into one number per day.
 */
function usePersonal(personal, state, view, values) {
  return useMemo(() => {
    if (!personal?.history?.data || !state.data || view.mode !== "range") return null;
    const daily = values([personal.history.data, state.data]);
    const ranges = personalRanges(daily, datesBetween(view.start, view.end));
    return { ranges, notes: PERSONAL[personal.notes] };
    // `values` is chosen by the card and does not change between renders.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [personal?.history?.data, personal?.notes, state.data, view.mode, view.start, view.end]);
}

/** The mean of each bucket as a line; the bucket's range shows on hover. */
export function StatCard({ title, note, explain, state, view, unit = "", digits = 0, bands, color, wide = false, personal }) {
  const { from, to } = useBounds(view);
  const [hidden, toggle] = useHidden();
  const rows = useMemo(
    () => (state.data ? statRows(state.data, view.start, view.end, view.resolution) : []),
    [state.data, view.start, view.end, view.resolution],
  );
  const series = useMemo(
    () => [{ id: "avg-line", label: title, color, points: rows.map((row) => ({ x: row.x, y: row.mid })) }],
    [rows, color, title],
  );
  const daily = view.resolution === "1d";
  const ranges = usePersonal(daily ? personal : null, state, view, dailyStatValues);
  const byTime = useMemo(() => new Map(rows.map((row) => [row.x.getTime(), row])), [rows]);
  const tipExtra = (x) => {
    const row = byTime.get(x.getTime());
    return row && row.low !== null
      ? `Range in this bucket ${formatNumber(row.low, digits)}–${formatNumber(row.high, digits)}${unit}`
      : null;
  };
  return (
    <Card
      title={title}
      note={note}
      explain={explain}
      states={[state]}
      empty={!hasBuckets(state.data)}
      legend={legendOf(series, ranges)}
      hidden={hidden}
      onToggle={toggle}
      wide={wide}
    >
      <TimeLine
        series={series}
        hidden={hidden}
        bands={bands}
        from={from}
        to={to}
        unit={unit}
        digits={digits}
        daily={view.resolution === "1d"}
        tipExtra={tipExtra}
        personal={ranges}
        onDay={view.mode === "range" ? view.onDay : undefined}
      />
    </Card>
  );
}

/** A total per bucket, as bars. */
export function SumCard({ title, note, explain, state, view, unit = "", digits = 0, scale = 1, color, format }) {
  const [hidden, toggle] = useHidden();
  const rows = useMemo(
    () => (state.data ? sumRows(state.data, view.start, view.end, view.resolution, scale) : []),
    [state.data, view.start, view.end, view.resolution, scale],
  );
  const keys = useMemo(() => [{ key: "value", label: title, color }], [title, color]);
  return (
    <Card
      title={title}
      note={note}
      explain={explain}
      states={[state]}
      empty={!hasBuckets(state.data)}
      legend={REFERENCE_KEYS}
      hidden={hidden}
      onToggle={toggle}
    >
      <Bars
        rows={rows}
        keys={keys}
        hidden={hidden}
        unit={unit}
        digits={digits}
        format={format}
        onDay={view.mode === "range" ? view.onDay : undefined}
      />
    </Card>
  );
}

/** Plain daily bars from rows the caller built. */
export function BarsCard({ title, note, explain, state, rows, color, format, unit = "", digits = 0, yFormat, emptyText, empty, onDay }) {
  const [hidden, toggle] = useHidden();
  const keys = useMemo(() => [{ key: "value", label: title, color }], [title, color]);
  return (
    <Card
      title={title}
      note={note}
      explain={explain}
      states={[state]}
      empty={empty ?? rows.every((row) => !row.value)}
      emptyText={emptyText}
      legend={REFERENCE_KEYS}
      hidden={hidden}
      onToggle={toggle}
    >
      <Bars
        rows={rows}
        keys={keys}
        hidden={hidden}
        daily
        format={format}
        unit={unit}
        digits={digits}
        yFormat={yFormat}
        onDay={onDay}
      />
    </Card>
  );
}

/**
 * Minutes per category, such as heart-rate zones. Over a range: one sub-tab
 * per category, its minutes compared across the days. Over a day: one lane per
 * category, with back-to-back buckets merged into blocks.
 */
export function CategoryCard({ title, note, explain, state, view, order, labels, colors }) {
  const categories = useMemo(() => presentCategories(state.data, order), [state.data, order]);
  const [chosen, setChosen] = useState(null);
  const [hidden, toggle] = useHidden();
  const active = categories.includes(chosen) ? chosen : categories[0];

  const rows = useMemo(
    () => (state.data && active ? categoryRows(state.data, view.start, view.end, view.resolution, [active]) : []),
    [state.data, view.start, view.end, view.resolution, active],
  );
  const lanes = useMemo(
    () =>
      view.mode === "day"
        ? categoryLanes(state.data, categories, view.resolution).map(({ category, spans }) => ({
            id: category,
            label: labels[category] ?? category,
            color: colors[category],
            spans,
          }))
        : [],
    [view.mode, state.data, categories, view.resolution, labels, colors],
  );
  const totals = useMemo(() => {
    const sums = {};
    for (const bucket of state.data?.buckets ?? []) {
      for (const [name, minutes] of Object.entries(bucket.totals)) sums[name] = (sums[name] ?? 0) + minutes;
    }
    return sums;
  }, [state.data]);

  if (view.mode === "day") {
    return (
      <Card
        title={title}
        note={note ?? "Hover a block for its times. Back-to-back buckets are merged."}
        explain={explain}
        states={[state]}
        empty={!hasBuckets(state.data)}
        height="auto"
        wide
      >
        <Lanes lanes={lanes} label={title} />
      </Card>
    );
  }

  const keys = active ? [{ key: active, label: labels[active] ?? active, color: colors[active] }] : [];
  return (
    <Card
      title={title}
      note={note}
      explain={explain}
      states={[state]}
      empty={!hasBuckets(state.data)}
      legend={REFERENCE_KEYS}
      hidden={hidden}
      onToggle={toggle}
      toolbar={
        <Tabs
          value={active ?? false}
          onChange={(_, value) => setChosen(value)}
          variant="scrollable"
          scrollButtons={false}
          className="subtabs"
          slotProps={{ indicator: { style: { backgroundColor: colors[active] } } }}
        >
          {categories.map((category) => (
            <Tab
              key={category}
              value={category}
              label={
                <span className="subtab">
                  <span className="swatch block" style={{ "--swatch": colors[category] }} aria-hidden="true" />
                  {labels[category] ?? category}
                  <span className="subtab-total">{formatMinutes(totals[category])}</span>
                </span>
              }
            />
          ))}
        </Tabs>
      }
    >
      <Bars
        rows={rows}
        keys={keys}
        hidden={hidden}
        unit=" min"
        format={(value) => formatMinutes(value)}
        onDay={view.onDay}
      />
    </Card>
  );
}

/** Daily readings, one line per field. All fields must share a unit. */
export function ReadingsCard({ title, note, explain, state, view, fields, unit = "", digits = 0, scale = 1, personal }) {
  const { from, to } = useBounds(view);
  const [hidden, toggle] = useHidden();
  const series = useMemo(
    () =>
      readingSeries(state.data, fields, scale).map((line) => ({
        ...line,
        color: fields.find((f) => f.field === line.id).color,
      })),
    [state.data, fields, scale],
  );
  const empty = !hasReadings(state.data) || series.every((line) => line.points.length === 0);
  const ranges = usePersonal(personal, state, view, (payloads) =>
    new Map(
      [...dailyReadingValues(payloads, fields[0].field).entries()].map(([day, value]) => [day, value * scale]),
    ),
  );
  return (
    <Card
      title={title}
      note={note}
      explain={explain}
      states={[state]}
      empty={empty}
      legend={legendOf(series, ranges)}
      hidden={hidden}
      onToggle={toggle}
    >
      <TimeLine
        series={series}
        hidden={hidden}
        from={from}
        to={to}
        unit={unit}
        digits={digits}
        daily
        personal={ranges}
        onDay={view.mode === "range" ? view.onDay : undefined}
      />
    </Card>
  );
}

/** Daily readings of a middle value, with the bounds shown on hover. */
export function ReadingBandCard({ title, note, explain, state, view, fields, labels, unit = "", digits = 0, color, personal }) {
  const { from, to } = useBounds(view);
  const [hidden, toggle] = useHidden();
  const rows = useMemo(
    () => readingBandRows(state.data, fields, view.start, view.end),
    [state.data, fields, view.start, view.end],
  );
  const series = useMemo(
    () => [{ id: "mid", label: labels.mid, color, points: rows.map((r) => ({ x: r.x, y: r.mid })) }],
    [rows, labels.mid, color],
  );
  const ranges = usePersonal(personal, state, view, (payloads) => dailyReadingValues(payloads, fields.mid));
  const byTime = useMemo(() => new Map(rows.map((row) => [row.x.getTime(), row])), [rows]);
  const tipExtra = (x) => {
    const row = byTime.get(x.getTime());
    return row && row.low !== null
      ? `${labels.low} ${formatNumber(row.low, digits)}${unit} · ${labels.high} ${formatNumber(row.high, digits)}${unit}`
      : null;
  };
  return (
    <Card
      title={title}
      note={note}
      explain={explain}
      states={[state]}
      empty={!hasReadings(state.data)}
      legend={legendOf(series, ranges)}
      hidden={hidden}
      onToggle={toggle}
    >
      <TimeLine
        series={series}
        hidden={hidden}
        from={from}
        to={to}
        unit={unit}
        digits={digits}
        daily
        tipExtra={tipExtra}
        personal={ranges}
        onDay={view.mode === "range" ? view.onDay : undefined}
      />
    </Card>
  );
}

/** Hour by day, from an hourly series. Only drawn when the range is bucketed hourly. */
export function HeatmapCard({ title, note, explain, state, view, pick, format }) {
  const rows = useMemo(
    () => (state.data ? hourByDay(state.data, view.start, view.end, pick) : []),
    [state.data, view.start, view.end, pick],
  );
  const days = datesBetween(view.start, view.end).length;
  return (
    <Card
      title={title}
      note={note}
      explain={explain}
      states={[state]}
      empty={!hasBuckets(state.data)}
      height={heatmapHeight(days)}
      wide
    >
      <HourHeatmap rows={rows} format={format} onDay={view.onDay} />
    </Card>
  );
}

/** A few headline values in a row, for a single day or the latest reading. */
export function Figures({ title, note, explain, states = [], items, emptyText }) {
  const shown = items.filter((item) => item.value !== null && item.value !== undefined);
  return (
    <Card
      title={title}
      note={note}
      explain={explain}
      states={states}
      empty={shown.length === 0}
      emptyText={emptyText}
      height="auto"
    >
      <dl className="figures">
        {shown.map((item) => (
          <div key={item.label}>
            <dt>{item.label}</dt>
            <dd>
              <span className="figure">
                {typeof item.value === "number" ? formatNumber(item.value, item.digits ?? 0) : item.value}
              </span>
              {item.unit && <span className="figure-unit"> {item.unit}</span>}
            </dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}
