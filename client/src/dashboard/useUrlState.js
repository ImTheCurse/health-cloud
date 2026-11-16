import { useCallback, useEffect, useState } from "react";

import { GROUP_IDS } from "./groups/index.js";

export const RANGES = ["7", "30", "90"];
export const BUCKETS = ["1h", "1d"];
export const DAY_RESOLUTIONS = ["1m", "5m", "10m", "30m", "1h"];

const DEFAULTS = { group: "heart", range: "7", bucket: "1h", day: null, res: "1h" };
const ALLOWED = {
  group: GROUP_IDS,
  range: RANGES,
  bucket: BUCKETS,
  res: DAY_RESOLUTIONS,
};
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function read() {
  const params = new URLSearchParams(window.location.search);
  const state = { ...DEFAULTS };
  for (const [name, allowed] of Object.entries(ALLOWED)) {
    const value = params.get(name);
    if (allowed.includes(value)) state[name] = value;
  }
  const day = params.get("day");
  if (day && ISO_DATE.test(day)) state.day = day;
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
 * The dashboard's view -- tab, range, bucket size, open day -- kept in the
 * query string, so a reload or a shared link lands on the same view. Opening
 * and leaving a day are history entries, so the browser's back button works.
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
      write(next, push);
      return next;
    });
  }, []);

  return [state, update];
}
