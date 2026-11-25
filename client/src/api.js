// The container serves /config.js with the address it was started with, so one
// image works for any deployment. Under `npm run dev` that file is empty and
// the Vite variable applies.
export const API_BASE =
  window.__CONFIG__?.apiBaseUrl ||
  import.meta.env.VITE_API_BASE_URL ||
  "http://localhost:8000";

// Google redirects the browser itself, so this is a navigation, not a fetch.
export const connectUrl = `${API_BASE}/auth/google/login`;

// Every call carries the session cookie, which the API allows by listing this
// origin explicitly -- a wildcard is refused when credentials are included.
async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    ...options,
  });
  if (response.status === 401) return null;
  if (!response.ok) throw new Error(`${path} returned ${response.status}`);
  return response.json();
}

export async function fetchAccount() {
  const [account, connection] = await Promise.all([
    request("/auth/me"),
    request("/auth/status"),
  ]);
  if (!account || !connection) return null;
  return { ...account, ...connection };
}

export function signOut() {
  return request("/auth/logout", { method: "POST" });
}

/** One `/data/*` route. Null when the session has gone. */
export function fetchData(path, params, signal) {
  const query = new URLSearchParams(params).toString();
  return request(`/data${path}?${query}`, { signal });
}

// Sent on every request that changes something. The API refuses those without
// it: a form on another site cannot set a header.
const CHANGES = { "X-Requested-With": "health-cloud" };

/** Starts a backfill of the last day. Resolves to `{ run_id }`. */
export function startBackfill() {
  return request("/backfill", { method: "POST", headers: CHANGES });
}

/** How a backfill run is going: `{ state }`, one of running, completed, failed. */
export function fetchBackfill(runId) {
  return request(`/backfill/${encodeURIComponent(runId)}`);
}
