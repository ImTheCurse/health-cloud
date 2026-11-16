import { useCallback, useEffect, useSyncExternalStore } from "react";

import { isRefreshing, keyOf, lastRefreshedAt, load, snapshot, subscribe } from "./dataStore.js";

const LOADING = { status: "loading", data: null, error: null };
const IDLE = { status: "idle", data: null, error: null };

// One stable result object per stored entry state, so React sees no change
// until the entry itself does.
const results = new WeakMap();

function resultOf(entry) {
  if (!entry || (!entry.at && !entry.data)) return LOADING;
  const cached = results.get(entry);
  if (cached && cached.data === entry.data && cached.error === entry.error) return cached;
  const result = entry.error
    ? { status: "error", data: null, error: entry.error }
    : { status: "ready", data: entry.data, error: null };
  results.set(entry, result);
  return result;
}

/**
 * One `/data/*` route, from the shared in-memory store. Pass `params` as null
 * to skip it. Returns `{ status, data, error }`.
 */
export function useData(path, params) {
  const key = params ? keyOf(path, params) : null;

  useEffect(() => {
    if (key) load(path, params);
    // `key` is `path` and `params` serialised, so it is the whole dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const get = useCallback(() => (key ? resultOf(snapshot(key)) : IDLE), [key]);
  return useSyncExternalStore(subscribe, get);
}

/** When the store last heard back from the API, and whether it is busy now. */
export function useRefreshState() {
  const at = useSyncExternalStore(subscribe, lastRefreshedAt);
  const busy = useSyncExternalStore(subscribe, isRefreshing);
  return { at, busy };
}
