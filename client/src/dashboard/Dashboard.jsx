import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import RefreshIcon from "@mui/icons-material/Refresh";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";
import { DatePicker } from "@mui/x-date-pickers/DatePicker";
import dayjs from "dayjs";
import { useCallback, useEffect, useMemo } from "react";

import { ChartModeContext } from "./chartMode.js";
import { preload, REFRESH_MS, refreshAll } from "./dataStore.js";
import { addDays, parseIsoDate, today } from "./dates.js";
import { formatDay, formatFullDay, formatTime } from "./format.js";
import { GROUPS } from "./groups/index.js";
import Home from "./Home.jsx";
import { ROUTES } from "./routes.js";
import {
  clampStart,
  endDay,
  MAX_CUSTOM_DAYS,
  MAX_HOURLY_DAYS,
  rangeBucket,
  SPAN_LABELS,
  SPANS,
  spanDays,
  startDay,
  viewOf,
} from "./spans.js";
import { useRefreshState } from "./useData.js";
import { BUCKETS, DAY_RESOLUTIONS, useUrlState } from "./useUrlState.js";

const BUCKET_LABELS = { "1h": "Hourly", "1d": "Daily" };
const RESOLUTION_LABELS = { "1m": "1 min", "5m": "5 min", "10m": "10 min", "30m": "30 min", "1h": "1 hour" };

/** A day for the URL: today is left out, so a bookmark keeps meaning today. */
function dayParam(day) {
  return day >= today() ? null : day;
}

/**
 * The home page by default; a group's charts once one is chosen, over a day,
 * a preset span or a custom range ending on the chosen day.
 */
export default function Dashboard() {
  const [state, update] = useUrlState();

  // Every five minutes, quietly re-fetch everything held.
  useEffect(() => {
    const timer = window.setInterval(refreshAll, REFRESH_MS);
    return () => window.clearInterval(timer);
  }, []);

  const setDay = useCallback((day) => update({ day: dayParam(day) }, { push: true }), [update]);
  const openGroup = useCallback(
    (group, patch = {}) => update({ group, chart: null, ...patch }, { push: true }),
    [update],
  );

  if (!state.group) {
    return (
      <div className="dashboard">
        <div className="controls">
          <DayControl day={endDay(state)} step={1} onChange={setDay} label="Day" />
          <RefreshControl />
        </div>
        <Home day={endDay(state)} onOpen={openGroup} />
      </div>
    );
  }

  return <GroupPage state={state} update={update} setDay={setDay} openGroup={openGroup} />;
}

function GroupPage({ state, update, setDay, openGroup }) {
  const group = GROUPS.find((candidate) => candidate.id === state.group) ?? GROUPS[0];

  const openDay = useCallback(
    (day) => update({ span: "day", day: dayParam(day) }, { push: true }),
    [update],
  );

  const view = useMemo(() => viewOf(state, group, openDay), [group, state, openDay]);

  // Other tabs' views, fetched in the background once the open tab has
  // finished loading, cheapest first. The store skips the raw-sample routes.
  useEffect(() => {
    const requests = GROUPS.filter((other) => other.id !== group.id).flatMap((other) =>
      Object.values(ROUTES[other.id](viewOf(state, other, openDay))),
    );
    preload(requests);
  }, [group, state, openDay]);

  // Opened from a home tile: bring its card into view and mark it briefly.
  useEffect(() => {
    if (!state.focus) return;
    const card = document.querySelector(`.cards [data-explain="${state.focus}"]`);
    // Cleared at once, so a reload or the back button does not scroll again.
    update({ focus: null });
    if (!card) return;
    card.scrollIntoView({ behavior: "smooth", block: "center" });
    card.classList.add("card-focus");
    window.setTimeout(() => card.classList.remove("card-focus"), 1800);
  }, [state.focus, update]);

  const changeSpan = (span) => {
    if (!span) return;
    // A custom range starts as whatever was on screen.
    update(span === "custom" ? { span, from: startDay(state) } : { span });
  };

  const openChart = useCallback((chart) => update({ chart }, { push: true }), [update]);
  const chartMode = useMemo(
    () =>
      state.chart
        ? { mode: "detail", chart: state.chart, onOpen: null }
        : { mode: "preview", chart: null, onOpen: openChart },
    [state.chart, openChart],
  );

  const { Component } = group;
  const days = spanDays(state);

  return (
    <div className="dashboard">
      <div className="group-nav">
        {state.chart ? (
          <Button
            variant="outlined"
            color="primary"
            size="small"
            startIcon={<ArrowBackIcon fontSize="small" />}
            onClick={() => update({ chart: null }, { push: true })}
          >
            {group.label}
          </Button>
        ) : (
          <GroupNav group={group} update={update} openGroup={openGroup} />
        )}
      </div>

      <div className="controls">
        <ToggleButtonGroup
          size="small"
          exclusive
          value={state.span}
          onChange={(_, span) => changeSpan(span)}
          aria-label="Span"
        >
          {SPANS.map((span) => (
            <ToggleButton key={span} value={span}>
              {SPAN_LABELS[span]}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>

        {state.span === "custom" ? (
          <CustomRange state={state} update={update} />
        ) : (
          <DayControl
            day={endDay(state)}
            start={state.span === "day" ? null : startDay(state)}
            step={days}
            onChange={setDay}
            label={state.span === "day" ? "Day" : "Ending"}
          />
        )}

        {group.bucketed && state.span === "day" && (
          <ToggleButtonGroup
            size="small"
            exclusive
            value={state.res}
            onChange={(_, res) => res && update({ res })}
            aria-label="Bucket size"
          >
            {DAY_RESOLUTIONS.map((res) => (
              <ToggleButton key={res} value={res}>
                {RESOLUTION_LABELS[res]}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
        )}

        {group.bucketed && state.span !== "day" && days <= MAX_HOURLY_DAYS && (
          <ToggleButtonGroup
            size="small"
            exclusive
            value={rangeBucket(state)}
            onChange={(_, bucket) => bucket && update({ bucket })}
            aria-label="Bucket size"
          >
            {BUCKETS.map((bucket) => (
              <ToggleButton key={bucket} value={bucket}>
                {BUCKET_LABELS[bucket]}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
        )}

        <RefreshControl />
      </div>

      <ChartModeContext.Provider value={chartMode}>
        <div
          className={state.chart ? "cards detail" : "cards preview"}
          key={`${group.id}-${state.chart}-${view.mode}-${view.start}-${view.end}`}
          data-empty-text="This chart has nothing to show at this span. Try another span, or go back."
        >
          <Component view={view} />
        </div>
      </ChartModeContext.Provider>
    </div>
  );
}

/** Home, and a tab per group. */
function GroupNav({ group, update, openGroup }) {
  return (
    <>
      <Button
        variant="outlined"
        color="primary"
        size="small"
        startIcon={<ArrowBackIcon fontSize="small" />}
        onClick={() => openGroup(null)}
      >
        Home
      </Button>
      <Tabs
        value={group.id}
        onChange={(_, id) => update({ group: id, chart: null })}
        variant="scrollable"
        scrollButtons="auto"
        aria-label="Measurements"
        className="tabs"
      >
        {GROUPS.map((candidate) => (
          <Tab key={candidate.id} value={candidate.id} label={candidate.label} />
        ))}
      </Tabs>
    </>
  );
}

/**
 * The day a view ends on: ‹ › step back and forward by the span's length, and
 * the picker jumps anywhere. Over a range the title reads "start – end".
 */
function DayControl({ day, start = null, step, onChange, label }) {
  const isToday = day >= today();
  const title = start
    ? `${formatDay(parseIsoDate(start))} – ${formatDay(parseIsoDate(day))}`
    : formatFullDay(parseIsoDate(day));
  const forward = addDays(day, step);

  return (
    <>
      <div className="day-stepper">
        <IconButton aria-label="Earlier" onClick={() => onChange(addDays(day, -step))}>
          <ChevronLeftIcon fontSize="small" />
        </IconButton>
        <span className="day-title">{title}</span>
        <IconButton
          aria-label="Later"
          disabled={isToday}
          onClick={() => onChange(forward > today() ? today() : forward)}
        >
          <ChevronRightIcon fontSize="small" />
        </IconButton>
      </div>
      <DatePicker
        label={label}
        value={dayjs(day)}
        maxDate={dayjs(today())}
        onChange={(value) => value?.isValid() && onChange(value.format("YYYY-MM-DD"))}
        slotProps={{ textField: { size: "small", className: "day-picker" } }}
      />
    </>
  );
}

/** A start and an end picker, at most MAX_CUSTOM_DAYS apart. */
function CustomRange({ state, update }) {
  const end = endDay(state);
  const start = startDay(state);

  const setStart = (value) => {
    if (!value?.isValid()) return;
    update({ from: clampStart(value.format("YYYY-MM-DD"), end) }, { push: true });
  };

  // Moving the end keeps the start where it was, unless that would break the cap.
  const setEnd = (value) => {
    if (!value?.isValid()) return;
    const day = value.format("YYYY-MM-DD");
    update({ day: dayParam(day), from: clampStart(start, day) }, { push: true });
  };

  return (
    <div className="custom-range">
      <DatePicker
        label="From"
        value={dayjs(start)}
        minDate={dayjs(addDays(end, 1 - MAX_CUSTOM_DAYS))}
        maxDate={dayjs(end)}
        onChange={setStart}
        slotProps={{ textField: { size: "small", className: "day-picker" } }}
      />
      <span className="hint">to</span>
      <DatePicker
        label="To"
        value={dayjs(end)}
        maxDate={dayjs(today())}
        onChange={setEnd}
        slotProps={{ textField: { size: "small", className: "day-picker" } }}
      />
    </div>
  );
}

/**
 * When data last arrived, and a button to fetch it again. Its own component,
 * so a request finishing re-renders this and not every chart on the page.
 */
function RefreshControl() {
  const { at, busy } = useRefreshState();
  return (
    <div className="refresh">
      {at && <span className="hint">Updated {formatTime(at)}</span>}
      <Tooltip title="Fetch the latest data now. It also refreshes every 5 minutes.">
        <span>
          <IconButton aria-label="Refresh" onClick={refreshAll} disabled={busy}>
            <RefreshIcon fontSize="small" className={busy ? "spinning" : undefined} />
          </IconButton>
        </span>
      </Tooltip>
    </div>
  );
}
