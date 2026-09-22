const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

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
