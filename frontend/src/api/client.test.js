import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { API_BASE_URL, ApiError, apiRequest, setUnauthorizedHandler, tokenStore } from "./client";

function response(status, body) {
  return {
    status,
    ok: status >= 200 && status < 300,
    statusText: "",
    json: async () => {
      if (body === undefined) throw new SyntaxError("no body");
      return body;
    },
  };
}

let fetchMock;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  setUnauthorizedHandler(null);
});

describe("apiRequest", () => {
  it("sends the bearer token and drops empty query params", async () => {
    tokenStore.set("abc123");
    fetchMock.mockResolvedValue(response(200, { items: [] }));

    const data = await apiRequest("/tickets", {
      query: { q: "sync", status: "", priority: undefined, assigned: null, page: 2 },
    });

    expect(data).toEqual({ items: [] });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${API_BASE_URL}/tickets?q=sync&page=2`);
    expect(init.method).toBe("GET");
    expect(init.headers.Authorization).toBe("Bearer abc123");
    expect(init.body).toBeUndefined();
  });

  it("sends no Authorization header without a token", async () => {
    fetchMock.mockResolvedValue(response(200, {}));

    await apiRequest("/kb/search");

    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBeUndefined();
  });

  it("sends JSON bodies", async () => {
    fetchMock.mockResolvedValue(response(201, { id: 1 }));

    await apiRequest("/tickets", { method: "POST", body: { title: "Help me" } });

    const init = fetchMock.mock.calls[0][1];
    expect(init.method).toBe("POST");
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(init.body).toBe(JSON.stringify({ title: "Help me" }));
  });

  it("sends FormData as-is, letting the browser set the multipart header", async () => {
    fetchMock.mockResolvedValue(response(202, { id: 9 }));
    const form = new FormData();
    form.append("title", "Guide");

    await apiRequest("/kb/documents", { method: "POST", form });

    const init = fetchMock.mock.calls[0][1];
    expect(init.body).toBe(form);
    expect(init.headers["Content-Type"]).toBeUndefined();
  });

  it("turns the error envelope into an ApiError", async () => {
    fetchMock.mockResolvedValue(
      response(409, {
        error: {
          code: "INVALID_TRANSITION",
          message: "Invalid status transition",
          details: { allowed: ["resolved"] },
        },
      }),
    );

    const error = await apiRequest("/tickets/1/status", { method: "POST", body: {} }).catch(
      (e) => e,
    );

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 409,
      code: "INVALID_TRANSITION",
      message: "Invalid status transition",
      details: { allowed: ["resolved"] },
    });
  });

  it("ends the session on a 401 for a request that carried a token", async () => {
    tokenStore.set("expired-token");
    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);
    fetchMock.mockResolvedValue(
      response(401, { error: { code: "INVALID_TOKEN", message: "Invalid or expired token" } }),
    );

    await expect(apiRequest("/auth/me")).rejects.toMatchObject({ code: "INVALID_TOKEN" });

    expect(tokenStore.get()).toBeNull();
    expect(onUnauthorized).toHaveBeenCalledOnce();
    expect(onUnauthorized.mock.calls[0][0].status).toBe(401);
  });

  it("does not end a session for a failed login (no token was sent)", async () => {
    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);
    fetchMock.mockResolvedValue(
      response(401, { error: { code: "INVALID_CREDENTIALS", message: "Invalid email or password" } }),
    );

    await expect(
      apiRequest("/auth/login", { method: "POST", body: { email: "a@b.c", password: "x" } }),
    ).rejects.toMatchObject({ code: "INVALID_CREDENTIALS" });

    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("returns null for 204 No Content", async () => {
    fetchMock.mockResolvedValue(response(204));

    await expect(apiRequest("/kb/documents/3", { method: "DELETE" })).resolves.toBeNull();
  });

  it("reports an unreachable server as a network error", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(apiRequest("/tickets")).rejects.toMatchObject({
      status: 0,
      code: "NETWORK_ERROR",
    });
  });
});
