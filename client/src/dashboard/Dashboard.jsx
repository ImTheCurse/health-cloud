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

import { load, REFRESH_MS, refreshAll } from "./dataStore.js";
import { addDays, dayRange, parseIsoDate, rangeEndingToday, today } from "./dates.js";
import { formatFullDay, formatTime } from "./format.js";
import { GROUPS } from "./groups/index.js";
import { ROUTES } from "./routes.js";
import { useRefreshState } from "./useData.js";
import { BUCKETS, DAY_RESOLUTIONS, RANGES, useUrlState } from "./useUrlState.js";

const RANGE_LABELS = { 7: "7 days", 30: "30 days", 90: "90 days" };
const BUCKET_LABELS = { "1h": "Hourly", "1d": "Daily" };
const RESOLUTION_LABELS = { "1m": "1 min", "5m": "5 min", "10m": "10 min", "30m": "30 min", "1h": "1 hour" };

function rangeView(group, state, onDay) {
  const days = Number(state.range);
  return {
    mode: "range",
    ...rangeEndingToday(days),
    resolution: group.bucketed ? state.bucket : "1d",
    days,
    onDay,
  };
}

/**
 * The measurements, one tab per kind. A range of days by default; a day opens
 * from the date picker or by clicking any chart, at a finer bucket size.
 */
export default function Dashboard() {
  const [state, update] = useUrlState();
  const group = GROUPS.find((candidate) => candidate.id === state.group) ?? GROUPS[0];

  const openDay = useCallback((day) => update({ day }, { push: true }), [update]);
  const closeDay = useCallback(() => update({ day: null }, { push: true }), [update]);

  const view = useMemo(() => {
    if (state.day) {
      return { mode: "day", ...dayRange(state.day), resolution: state.res, days: 1, onDay: openDay };
    }
    return rangeView(group, state, openDay);
  }, [group, state, openDay]);

  // Every five minutes, quietly re-fetch everything held.
  useEffect(() => {
    const timer = window.setInterval(refreshAll, REFRESH_MS);
    return () => window.clearInterval(timer);
  }, []);

  // Once the open tab has asked for its data, fetch the other tabs' range view
  // in the background, so switching tabs shows data straight away.
  useEffect(() => {
    const timer = window.setTimeout(() => {
      for (const other of GROUPS) {
        const otherView = rangeView(other, state, openDay);
        for (const [path, params] of Object.values(ROUTES[other.id](otherView))) {
          if (params) load(path, params);
        }
      }
    }, 800);
    return () => window.clearTimeout(timer);
  }, [state, openDay]);

  const { Component } = group;
  const maxDay = dayjs(today());

  return (
    <div className="dashboard">
      <Tabs
        value={group.id}
        onChange={(_, id) => update({ group: id })}
        variant="scrollable"
        scrollButtons="auto"
        aria-label="Measurements"
        className="tabs"
      >
        {GROUPS.map((candidate) => (
          <Tab key={candidate.id} value={candidate.id} label={candidate.label} />
        ))}
      </Tabs>

      <div className="controls">
        {state.day ? (
          <>
            <Button variant="outlined" color="primary" size="small" onClick={closeDay}>
              ← Back to {RANGE_LABELS[state.range]}
            </Button>
            <div className="day-stepper">
              <IconButton aria-label="Previous day" onClick={() => openDay(addDays(state.day, -1))}>
                <ChevronLeftIcon fontSize="small" />
              </IconButton>
              <span className="day-title">{formatFullDay(parseIsoDate(state.day))}</span>
              <IconButton
                aria-label="Next day"
                disabled={state.day >= today()}
                onClick={() => openDay(addDays(state.day, 1))}
              >
                <ChevronRightIcon fontSize="small" />
              </IconButton>
            </div>
            {group.bucketed && (
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
          </>
        ) : (
          <>
            <ToggleButtonGroup
              size="small"
              exclusive
              value={state.range}
              onChange={(_, range) => range && update({ range })}
              aria-label="Range"
            >
              {RANGES.map((range) => (
                <ToggleButton key={range} value={range}>
                  {RANGE_LABELS[range]}
                </ToggleButton>
              ))}
            </ToggleButtonGroup>
            {group.bucketed && (
              <ToggleButtonGroup
                size="small"
                exclusive
                value={state.bucket}
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
          </>
        )}

        <DatePicker
          label="Open a day"
          value={state.day ? dayjs(state.day) : null}
          maxDate={maxDay}
          onChange={(value) => value?.isValid() && openDay(value.format("YYYY-MM-DD"))}
          slotProps={{ textField: { size: "small", className: "day-picker" } }}
        />

        <RefreshControl />
      </div>

      <div className="cards" key={`${group.id}-${state.day ?? "range"}`}>
        <Component view={view} />
      </div>
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
