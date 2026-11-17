// Every `/data/*` response, kept in memory for the life of the tab. A chart that
// asks for something already fetched gets it at once; a refresh re-fetches in
// the background and swaps the new data in, so nothing flashes back to
// "loading". Memory only: decrypted health values are never written to disk.

import { fetchData } from "../api.js";

export const REFRESH_MS = 5 * 60 * 1000;

// Routes that read raw samples, hundreds of thousands of rows a month. They are
// never preloaded: the server cannot drop a request the browser stops waiting
// for, so preloading them piles work up behind whatever is on screen.
const HEAVY = new Set([
  "/heart-rate",
  "/heart-rate/time-in-zone",
  "/heart-rate/variability",
  "/oxygen-saturation",
  "/activity/level",
  "/activity/zone-minutes",
]);
// Background requests at once, so a preload never competes hard with a tab.
const BACKGROUND_AT_ONCE = 2;

const entries = new Map(); // key -> { path, params, data, error, at, inflight, background, stale }
const watchers = new Map(); // key -> charts currently showing it
const listeners = new Set();
let queue = [];
let backgroundRunning = 0;
let lastRefresh = null;

export function keyOf(path, params) {
  return `${path}?${new URLSearchParams(params)}`;
}

function notify() {
  for (const listener of listeners) listener();
}

export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function snapshot(key) {
  return entries.get(key);
}

export function lastRefreshedAt() {
  return lastRefresh;
}

/** Mark `key` as on screen, for as long as the returned function is not called. */
export function watch(key) {
  watchers.set(key, (watchers.get(key) ?? 0) + 1);
  return () => {
    const left = (watchers.get(key) ?? 1) - 1;
    if (left > 0) watchers.set(key, left);
    else watchers.delete(key);
  };
}

/**
 * Fetch `path` unless it is cached, stale or already on its way. A chart's
 * request is foreground; preloading passes `background`, and a chart asking for
 * something already preloading takes it over as foreground.
 */
export function load(path, params, { force = false, background = false } = {}) {
  const key = keyOf(path, params);
  const entry = entries.get(key) ?? {
    path,
    params,
    data: null,
    error: null,
    at: 0,
    inflight: null,
    background,
    stale: false,
  };
  entries.set(key, entry);
  if (!background) entry.background = false;
  if (entry.inflight) return entry.inflight;
  if (!force && entry.at && !entry.stale) return Promise.resolve();

  entry.background = background;
  entry.stale = false;
  entry.inflight = fetchData(path, params)
    .then((data) => {
      if (data === null) throw new Error("Signed out. Reload to sign in again.");
      entry.data = data;
      entry.error = null;
    })
    .catch((error) => {
      // A failed background refresh keeps the data already on screen.
      if (!entry.data) entry.error = error;
    })
    .finally(() => {
      entry.at = Date.now();
      entry.inflight = null;
      lastRefresh = new Date();
      notify();
      pump();
    });
  notify();
  return entry.inflight;
}

/**
 * Fetch other tabs' data in the background, but only once nothing on screen is
 * still loading, cheapest first, a couple at a time, and never the raw-sample
 * routes. A later call replaces the queue: preloading follows the current view.
 */
export function preload(requests) {
  queue = requests
    .filter(([path, params]) => params && !HEAVY.has(path))
    .filter(([path, params]) => {
      const entry = entries.get(keyOf(path, params));
      return !entry || (!entry.at && !entry.inflight);
    })
    .sort(([, a], [, b]) => cost(a) - cost(b));
  pump();
}

/** Cheaper first: one value a day before bucketed series. */
function cost(params) {
  return params.resolution ? 1 : 0;
}

function foregroundBusy() {
  for (const entry of entries.values()) if (entry.inflight && !entry.background) return true;
  return false;
}

function pump() {
  while (queue.length && backgroundRunning < BACKGROUND_AT_ONCE && !foregroundBusy()) {
    const [path, params] = queue.shift();
    const entry = entries.get(keyOf(path, params));
    if (entry && (entry.at || entry.inflight)) continue;
    backgroundRunning += 1;
    load(path, params, { background: true }).finally(() => {
      backgroundRunning -= 1;
      pump();
    });
  }
}

/**
 * Refresh what is on screen now, quietly; everything else held is marked stale
 * and refreshes when it is next shown. Refreshing all of it at once would set
 * off every heavy read the tab has ever made.
 */
export function refreshAll() {
  const shown = [];
  for (const [key, entry] of entries) {
    if (watchers.has(key)) shown.push(load(entry.path, entry.params, { force: true }));
    else entry.stale = true;
  }
  return Promise.all(shown);
}

/** Whether a chart's data is being re-fetched, for the refresh button's spinner. */
export function isRefreshing() {
  for (const entry of entries.values()) if (entry.inflight && entry.data) return true;
  return false;
}
