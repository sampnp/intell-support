// Thin fetch wrapper: base URL, bearer token, the backend's error envelope, and 401 handling.

const TOKEN_KEY = "intell.token";

export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api"
).replace(/\/+$/, "");

/** An error response from the API, carrying its envelope: {error: {code, message, details}}. */
export class ApiError extends Error {
  constructor({ status, code, message, details = null }) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (token) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

let unauthorizedHandler = null;

/** Called when a request made with a token comes back 401 (expired or revoked session). */
export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = handler;
}

function buildUrl(path, query) {
  const url = new URL(`${API_BASE_URL}${path}`);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

/**
 * @param {string} path  e.g. "/tickets"
 * @param {{method?: string, query?: object, body?: unknown, form?: FormData}} options
 */
export async function apiRequest(path, { method = "GET", query, body, form } = {}) {
  const headers = {};
  const token = tokenStore.get();
  if (token) headers.Authorization = `Bearer ${token}`;

  let payload;
  if (form) {
    payload = form; // the browser sets the multipart boundary
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(buildUrl(path, query), { method, headers, body: payload });
  } catch {
    throw new ApiError({
      status: 0,
      code: "NETWORK_ERROR",
      message: "Cannot reach the server. Is the backend running?",
    });
  }

  if (response.status === 204) return null;
  const data = await response.json().catch(() => null);

  if (!response.ok) {
    const envelope = data?.error;
    const error = new ApiError({
      status: response.status,
      code: envelope?.code ?? "HTTP_ERROR",
      message: envelope?.message ?? (response.statusText || "Request failed"),
      details: envelope?.details ?? null,
    });
    // A failed login is also a 401, but only a request that carried a token ends a session.
    if (response.status === 401 && token) {
      tokenStore.clear();
      unauthorizedHandler?.(error);
    }
    throw error;
  }
  return data;
}
