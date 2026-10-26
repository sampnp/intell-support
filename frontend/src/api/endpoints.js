// One function per backend endpoint (docs/PLAN.md §8).
import { apiRequest } from "./client";

export const auth = {
  login: (credentials) => apiRequest("/auth/login", { method: "POST", body: credentials }),
  register: (data) => apiRequest("/auth/register", { method: "POST", body: data }),
  me: () => apiRequest("/auth/me"),
};

export const tickets = {
  list: (query) => apiRequest("/tickets", { query }),
  get: (id) => apiRequest(`/tickets/${id}`),
  create: (data) => apiRequest("/tickets", { method: "POST", body: data }),
  update: (id, data) => apiRequest(`/tickets/${id}`, { method: "PATCH", body: data }),
  changeStatus: (id, status) =>
    apiRequest(`/tickets/${id}/status`, { method: "POST", body: { status } }),
  assign: (id, agentId) =>
    apiRequest(`/tickets/${id}/assign`, { method: "POST", body: { agent_id: agentId } }),
  comments: (id) => apiRequest(`/tickets/${id}/comments`),
  addComment: (id, data) => apiRequest(`/tickets/${id}/comments`, { method: "POST", body: data }),
  events: (id) => apiRequest(`/tickets/${id}/events`),
  suggestions: (id) => apiRequest(`/tickets/${id}/suggestions`),
  refreshSuggestions: (id) =>
    apiRequest(`/tickets/${id}/suggestions/refresh`, { method: "POST" }),
};

export const dashboard = {
  agent: () => apiRequest("/dashboard/agent"),
};

export const users = {
  agents: () => apiRequest("/users/agents"),
};

export const kb = {
  search: (query) => apiRequest("/kb/search", { query }),
  documents: () => apiRequest("/kb/documents"),
  upload: (file, title) => {
    const form = new FormData();
    form.append("file", file);
    if (title) form.append("title", title);
    return apiRequest("/kb/documents", { method: "POST", form });
  },
  remove: (id) => apiRequest(`/kb/documents/${id}`, { method: "DELETE" }),
  reindex: (id) => apiRequest(`/kb/documents/${id}/reindex`, { method: "POST" }),
};
