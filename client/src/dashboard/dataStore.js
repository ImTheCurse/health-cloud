// Every `/data/*` response, kept in memory for the life of the tab. A chart that
// asks for something already fetched gets it at once; a refresh re-fetches in
// the background and swaps the new data in, so nothing flashes back to
// "loading". Memory only: decrypted health values are never written to disk.

import { fetchData } from "../api.js";

export const REFRESH_MS = 5 * 60 * 1000;

const entries = new Map(); // key -> { path, params, data, error, at, inflight }
const listeners = new Set();
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

/** Fetch `path` unless it is cached or already on its way. */
export function load(path, params, { force = false } = {}) {
  const key = keyOf(path, params);
  const entry = entries.get(key) ?? { path, params, data: null, error: null, at: 0, inflight: null };
  entries.set(key, entry);
  if (entry.inflight || (!force && entry.at)) return entry.inflight ?? Promise.resolve();

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
    });
  notify();
  return entry.inflight;
}

/** Re-fetch everything held, quietly; charts keep their data until it lands. */
export function refreshAll() {
  return Promise.all([...entries.values()].map((entry) => load(entry.path, entry.params, { force: true })));
}

/** Whether any request is on its way, for the refresh button's spinner. */
export function isRefreshing() {
  for (const entry of entries.values()) if (entry.inflight && entry.data) return true;
  return false;
}
