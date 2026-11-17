import AirIcon from "@mui/icons-material/Air";
import BedtimeIcon from "@mui/icons-material/Bedtime";
import BoltIcon from "@mui/icons-material/Bolt";
import DirectionsWalkIcon from "@mui/icons-material/DirectionsWalk";
import FavoriteIcon from "@mui/icons-material/Favorite";
import MonitorHeartIcon from "@mui/icons-material/MonitorHeart";
import RouteIcon from "@mui/icons-material/Route";
import ShowChartIcon from "@mui/icons-material/ShowChart";
import ThermostatIcon from "@mui/icons-material/Thermostat";
import WaterDropIcon from "@mui/icons-material/WaterDrop";
import ButtonBase from "@mui/material/ButtonBase";
import Chip from "@mui/material/Chip";
import Skeleton from "@mui/material/Skeleton";
import { useLayoutEffect, useMemo, useRef } from "react";

import { addDays, today } from "./dates.js";
import { formatMinutes, formatNumber } from "./format.js";
import { PERSONAL_WINDOW_DAYS } from "./series.js";
import { BASELINE_DAYS, READERS, summarise } from "./summary.js";
import { ABOVE, CHART, INK_SOFT, PERSONAL_TONE, RULE, STAGE, ZONE } from "./theme.js";
import { useData } from "./useData.js";

const hourly = (frame) => ({ ...frame, resolution: "1h" });
const plain = (frame) => frame;
const daily = (frame) => ({ ...frame, resolution: "1d" });

const number = (digits, unit) => ({
  value: (value) => formatNumber(value, digits),
  delta: (delta) => formatNumber(Math.abs(delta), digits),
  unit,
  digits,
});

/**
 * Every tile: where its number comes from, how to read and print it, which way
 * is usually better (`better`: "up", "down" or null for neither), and which
 * group and card a click opens. `focus` is the card's `explain` key. A
 * `cumulative` tile is a total, drawn as a bar filling up from zero. A
 * `history` tile reads the 30 days before as well, for its personal range.
 * A `historyRoute` reads those earlier days separately, at daily buckets, so
 * a heavy route shows its figure first and its range when the history lands.
 */
const RECOVERY = [
  {
    id: "sleep",
    history: true,
    label: "Sleep",
    Icon: BedtimeIcon,
    color: STAGE.DEEP,
    route: ["/sleep", plain],
    reader: READERS.sleep,
    format: {
      value: formatMinutes,
      delta: (delta) => formatMinutes(Math.abs(delta)),
      unit: null,
      digits: 0,
    },
    better: "up",
    group: "sleep",
    focus: "sleep",
  },
  {
    id: "resting",
    history: true,
    label: "Resting heart rate",
    Icon: MonitorHeartIcon,
    color: CHART.resting,
    route: ["/heart-rate/resting", plain],
    reader: READERS.reading("bpm"),
    format: number(0, "bpm"),
    better: "down",
    group: "heart",
    focus: "resting",
  },
  {
    id: "hrv",
    history: true,
    label: "HRV",
    Icon: ShowChartIcon,
    color: CHART.nightlyHrv,
    route: ["/heart-rate/variability/daily", plain],
    reader: READERS.reading("average_ms"),
    format: number(0, "ms"),
    better: "up",
    group: "heart",
    focus: "nightlyHrv",
  },
  {
    id: "temperature",
    history: true,
    label: "Skin temperature",
    Icon: ThermostatIcon,
    color: ABOVE,
    route: ["/sleep/temperature", plain],
    reader: READERS.temperature,
    format: {
      value: (value) => `${value > 0 ? "+" : value < 0 ? "−" : "±"}${formatNumber(Math.abs(value), 1)}`,
      delta: (delta) => formatNumber(Math.abs(delta), 1),
      unit: "°C vs baseline",
      digits: 1,
    },
    better: null,
    noArrow: true,
    group: "sleep",
    focus: "temperature",
  },
  {
    id: "breathing",
    history: true,
    label: "Breathing rate",
    Icon: AirIcon,
    color: CHART.breathing,
    route: ["/respiratory-rate/daily", plain],
    reader: READERS.reading("breaths_per_minute"),
    format: number(1, "breaths/min"),
    better: null,
    group: "breathing",
    focus: "breathing",
  },
  {
    id: "oxygen",
    history: true,
    label: "Blood oxygen",
    Icon: WaterDropIcon,
    color: CHART.oxygenNightly,
    route: ["/oxygen-saturation/daily", plain],
    reader: READERS.reading("average_percent"),
    format: number(1, "%"),
    better: "up",
    group: "breathing",
    focus: "oxygenNightly",
  },
];

const ACTIVITY = [
  {
    id: "steps",
    cumulative: true,
    label: "Steps",
    Icon: DirectionsWalkIcon,
    color: CHART.steps,
    route: ["/activity/steps", hourly],
    reader: READERS.sum,
    format: number(0, null),
    better: "up",
    group: "activity",
    focus: "steps",
  },
  {
    id: "distance",
    cumulative: true,
    label: "Distance",
    Icon: RouteIcon,
    color: CHART.distance,
    route: ["/activity/distance", hourly],
    reader: READERS.sum,
    scale: 1 / 1000,
    format: number(1, "km"),
    better: "up",
    group: "activity",
    focus: "distance",
  },
  {
    id: "azm",
    cumulative: true,
    label: "Active Zone Minutes",
    Icon: BoltIcon,
    color: ZONE.VIGOROUS,
    route: ["/activity/zone-minutes", hourly],
    reader: READERS.categories,
    format: number(0, "min"),
    better: "up",
    group: "activity",
    focus: "azm",
  },
  {
    id: "heartRate",
    label: "Heart rate average",
    Icon: FavoriteIcon,
    color: CHART.heartRate,
    route: ["/heart-rate", hourly],
    historyRoute: ["/heart-rate", daily],
    reader: READERS.mean,
    format: number(0, "bpm"),
    better: null,
    group: "heart",
    focus: "heartRate",
  },
];

/**
 * The first page: the day's most telling figures, activity first, then
 * recovery, each against your last seven days. A tile opens its group on that
 * day, at its card.
 */
export default function Home({ day, onOpen }) {
  const isToday = day >= today();
  const fill = useScreenFill();
  return (
    <div className="home" ref={fill}>
      <TileRow
        title="Activity"
        note={isToday ? "Last 24 hours" : "That day"}
        tiles={ACTIVITY}
        day={day}
        isToday={isToday}
        onOpen={onOpen}
      />
      <TileRow title="Recovery" note="Overnight" tiles={RECOVERY} day={day} isToday={isToday} onOpen={onOpen} />
    </div>
  );
}

function TileRow({ title, note, tiles, day, isToday, onOpen }) {
  return (
    <section className="tile-row" aria-label={title}>
      <h2 className="tile-row-title">
        {title} <span className="hint">{note}</span>
      </h2>
      <div className="tiles" data-count={tiles.length}>
        {tiles.map((tile) => (
          <Tile key={tile.id} tile={tile} day={day} isToday={isToday} onOpen={onOpen} />
        ))}
      </div>
    </section>
  );
}

// Space kept free below the tiles, in pixels.
const BOTTOM_GAP = 12;

/**
 * Sets `--fill` on the element to the height from its top to the bottom of the
 * window, so the grid can stretch its tiles to fill the screen exactly. Kept
 * current as the window resizes.
 */
function useScreenFill() {
  const ref = useRef(null);
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return undefined;
    const measure = () => {
      const top = element.getBoundingClientRect().top + window.scrollY;
      element.style.setProperty("--fill", `${Math.max(0, window.innerHeight - top - BOTTOM_GAP)}px`);
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);
  return ref;
}

function Tile({ tile, day, isToday, onOpen }) {
  const [path, paramsOf] = tile.route;
  // The day and the days before it that the comparison and the range need.
  const frame = useMemo(
    () => ({ start: addDays(day, -(tile.history ? PERSONAL_WINDOW_DAYS : BASELINE_DAYS)), end: addDays(day, 1) }),
    [day, tile.history],
  );
  const state = useData(path, paramsOf(frame));
  // The days before `frame`, back to a full personal-range window.
  const [historyPath, historyParamsOf] = tile.historyRoute ?? [path, null];
  const history = useData(
    historyPath,
    historyParamsOf ? historyParamsOf({ start: addDays(frame.start, BASELINE_DAYS - PERSONAL_WINDOW_DAYS), end: frame.start }) : null,
  );

  const summary = useMemo(() => {
    if (!state.data) return null;
    const raw = summarise(state.data, tile.reader, day, isToday, new Date(), history.data);
    const scale = tile.scale ?? 1;
    const scaled = (value) => (value === null ? null : value * scale);
    return {
      ...raw,
      value: scaled(raw.value),
      average: scaled(raw.average),
      usual: raw.usual && { low: scaled(raw.usual.low), high: scaled(raw.usual.high) },
      low: scaled(raw.low),
      high: scaled(raw.high),
    };
  }, [state.data, history.data, tile, day, isToday]);

  const { Icon, format } = tile;
  const open = () => onOpen(tile.group, { span: "day", focus: tile.focus });
  const shown = summary && summary.value !== null;

  return (
    <ButtonBase className="tile" onClick={open} aria-label={`${tile.label}: open details`}>
      <span className="tile-head">
        <Icon style={{ color: tile.color }} aria-hidden="true" />
        <span className="tile-label">{tile.label}</span>
        {shown && <Change tile={tile} summary={summary} />}
      </span>

      {state.status === "loading" && (
        <span className="tile-body" role="status" aria-live="polite">
          <Skeleton variant="text" width="55%" sx={{ fontSize: "2rem", bgcolor: RULE }} />
          <Skeleton variant="text" width="75%" sx={{ bgcolor: RULE }} />
          <Skeleton variant="rounded" height={12} sx={{ bgcolor: RULE }} />
        </span>
      )}

      {state.status === "error" && <span className="tile-body hint">Couldn't load this.</span>}

      {summary && summary.value === null && (
        <span className="tile-body">
          <span className="tile-value">
            <span className="figure">—</span>
          </span>
          <span className="hint">No data yet</span>
        </span>
      )}

      {shown && (
        <span className="tile-body">
          <span className="tile-value">
            <span className="figure">{format.value(summary.value)}</span>
            {format.unit && <span className="figure-unit"> {format.unit}</span>}
          </span>
          {tile.cumulative ? <FillBar tile={tile} summary={summary} /> : <RangeBar tile={tile} summary={summary} />}
        </span>
      )}
    </ButtonBase>
  );
}

/**
 * The change from the seven-day average, top right: arrow and size, blue where
 * that direction is usually better, orange where it is usually worse, grey
 * where neither.
 */
function Change({ tile, summary }) {
  const { value, average } = summary;
  if (average === null || tile.noArrow) return null;

  const delta = value - average;
  // A change too small to show at the tile's precision is no change.
  const steady = Math.abs(delta) < 0.5 * 10 ** -tile.format.digits;
  const up = delta > 0;
  const tone = steady || tile.better === null ? "neutral" : (tile.better === "up") === up ? "good" : "watch";
  const color = tone === "neutral" ? INK_SOFT : PERSONAL_TONE[tone];

  const label = steady ? (
    "= usual"
  ) : (
    <>
      <span aria-hidden="true">{up ? "▲" : "▼"}</span> {tile.format.delta(delta)}
      <span className="visually-hidden">{up ? " above" : " below"} the 7-day average</span>
    </>
  );
  return (
    <Chip
      className="tile-change"
      label={label}
      sx={{ color, bgcolor: `${color}1f`, borderColor: `${color}66` }}
      variant="outlined"
    />
  );
}

/**
 * Where the day sits against your usual: the personal range as a green band,
 * the 7-day average as a tick, and the day as a dot, in the tile's colour when
 * inside the range and blue or orange when outside it, by which side is
 * usually better. A caption gives the range in figures. Without enough history
 * for a range, the band is the past week's lowest to highest instead.
 */
function RangeBar({ tile, summary }) {
  const { value, average, low, high, usual } = summary;
  const band = usual ?? (average === null ? null : { low, high });
  if (!band) return <span className="range-caption hint">No week to compare with</span>;

  const marks = [value, band.low, band.high, ...(average === null ? [] : [average])];
  const pad = (Math.max(...marks) - Math.min(...marks) || 1) * 0.1;
  const from = Math.min(...marks) - pad;
  const to = Math.max(...marks) + pad;
  const at = (x) => `${((x - from) / (to - from)) * 100}%`;

  const side = value > band.high ? "above" : value < band.low ? "below" : null;
  let dot = tile.color;
  if (usual && side) {
    const good = tile.better !== null && (tile.better === "up") === (side === "above");
    dot = good ? PERSONAL_TONE.good : PERSONAL_TONE.watch;
  }
  const { format } = tile;
  const range = `${format.value(band.low)}–${format.value(band.high)}${format.unit ? ` ${format.unit}` : ""}`;
  const week = average === null ? null : <Average tile={tile} average={average} />;

  return (
    <span className="range">
      <span className="range-bar" aria-hidden="true">
        <span
          className={usual ? "range-band usual" : "range-band"}
          style={{ left: at(band.low), width: `calc(${at(band.high)} - ${at(band.low)})` }}
        />
        {average !== null && <span className="range-average" style={{ left: at(average) }} />}
        <span className="range-dot" style={{ left: at(value), background: dot }} />
      </span>
      <span className="range-caption hint">
        <span>
          {usual ? "Usual" : "This week"} {range}
          {usual && side && <b style={{ color: dot }}> · {side}</b>}
        </span>
        {week}
      </span>
    </span>
  );
}

/**
 * A total filling up from zero: full at the week's best day, or at the day
 * itself when it beats it, with the week's average as a tick.
 */
function FillBar({ tile, summary }) {
  const { value, average, high } = summary;
  const top = Math.max(value, high ?? 0, average ?? 0) || 1;
  const at = (x) => `${Math.min(100, (x / top) * 100)}%`;
  return (
    <span className="range">
      <span className="range-bar" aria-hidden="true">
        <span className="range-fill" style={{ width: at(value), background: tile.color }} />
        {average !== null && <span className="range-average" style={{ left: at(average) }} />}
      </span>
      <span className="range-caption hint">
        {average === null ? <span>No week to compare with</span> : <Average tile={tile} average={average} />}
      </span>
    </span>
  );
}

/** The 7-day average, beside the tick that marks it on the bar. */
function Average({ tile, average }) {
  return (
    <span className="range-week">
      <span className="range-tick" aria-hidden="true" /> 7-day avg {tile.format.value(average)}
    </span>
  );
}
