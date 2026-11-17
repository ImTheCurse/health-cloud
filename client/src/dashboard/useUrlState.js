import { useCallback, useEffect, useState } from "react";

import { GROUP_IDS } from "./groups/index.js";
import { clampStart, SPANS } from "./spans.js";

export const BUCKETS = ["1h", "1d"];
export const DAY_RESOLUTIONS = ["1m", "5m", "10m", "30m", "1h"];

// No group is the home page; no day is today.
// `focus` names a card to scroll to once a group opens, `chart` the card shown
// on its own page: both by its `explain` key.
const DEFAULTS = {
  group: null,
  chart: null,
  span: "week",
  day: null,
  from: null,
  bucket: "1h",
  res: "1h",
  focus: null,
};
const ALLOWED = {
  group: GROUP_IDS,
  span: SPANS,
  bucket: BUCKETS,
  res: DAY_RESOLUTIONS,
};
const DATES = ["day", "from"];
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const CARD_KEYS = ["focus", "chart"];
const CARD_KEY = /^[A-Za-z]+$/;

function read() {
  const params = new URLSearchParams(window.location.search);
  const state = { ...DEFAULTS };
  for (const [name, allowed] of Object.entries(ALLOWED)) {
    const value = params.get(name);
    if (allowed.includes(value)) state[name] = value;
  }
  for (const name of DATES) {
    const value = params.get(name);
    if (value && ISO_DATE.test(value)) state[name] = value;
  }
  for (const name of CARD_KEYS) {
    const value = params.get(name);
    if (value && CARD_KEY.test(value)) state[name] = value;
  }
  if (!state.group) state.chart = null;
  if (state.span === "custom") {
    if (!state.from) state.span = DEFAULTS.span;
    else if (state.day) state.from = clampStart(state.from, state.day);
  }
  if (state.span !== "custom") state.from = null;
  return state;
}

function write(state, push) {
  const params = new URLSearchParams(window.location.search);
  for (const [name, value] of Object.entries(state)) {
    if (value === null || value === DEFAULTS[name]) params.delete(name);
    else params.set(name, value);
  }
  const query = params.toString();
  const url = `${window.location.pathname}${query ? `?${query}` : ""}`;
  if (push) window.history.pushState(null, "", url);
  else window.history.replaceState(null, "", url);
}

/**
 * The dashboard's view -- page, span, the day it ends on, bucket size -- kept
 * in the query string, so a reload or a shared link lands on the same view.
 * Moving between pages and opening a day are history entries, so the
 * browser's back button works.
 */
export function useUrlState() {
  const [state, setState] = useState(read);

  useEffect(() => {
    const onPop = () => setState(read());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const update = useCallback((patch, { push = false } = {}) => {
    setState((current) => {
      const next = { ...current, ...patch };
      if (next.span !== "custom") next.from = null;
      write(next, push);
      return next;
    });
  }, []);

  return [state, update];
}
