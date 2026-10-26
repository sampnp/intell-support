import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { tickets } from "../api/endpoints";
import { ErrorBanner, PriorityBadge, Spinner, StatusBadge } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import {
  CATEGORIES,
  CATEGORY_LABELS,
  PRIORITIES,
  PRIORITY_LABELS,
  STATUSES,
  STATUS_LABELS,
  formatRelative,
} from "../lib/format";

const PAGE_SIZE = 20;
const FILTERS = ["q", "status", "priority", "category", "assigned"];

function Select({ label, value, onChange, options }) {
  return (
    <label className="text-sm">
      <span className="sr-only">{label}</span>
      <select className="input" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{label}: all</option>
        {options.map(([optionValue, optionLabel]) => (
          <option key={optionValue} value={optionValue}>
            {optionLabel}
          </option>
        ))}
      </select>
    </label>
  );
}

export default function TicketListPage() {
  const { isAgent } = useAuth();
  // Filters live in the URL so a filtered list can be bookmarked and survives a reload.
  const [params, setParams] = useSearchParams();
  const filters = Object.fromEntries(FILTERS.map((key) => [key, params.get(key) ?? ""]));
  const page = Math.max(1, Number(params.get("page")) || 1);
  const [search, setSearch] = useState(filters.q);

  const setFilter = (key, value) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete("page");
    setParams(next, { replace: true });
  };

  // Debounce typing in the search box.
  useEffect(() => {
    if (search === filters.q) return undefined;
    const timer = setTimeout(() => setFilter("q", search.trim()), 300);
    return () => clearTimeout(timer);
  }, [search]); // eslint-disable-line react-hooks/exhaustive-deps

  const query = useQuery({
    queryKey: ["tickets", filters, page],
    queryFn: () => tickets.list({ ...filters, page, page_size: PAGE_SIZE }),
    placeholderData: keepPreviousData,
  });

  const total = query.data?.total ?? 0;
  const lastPage = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const goTo = (target) => {
    const next = new URLSearchParams(params);
    next.set("page", String(target));
    setParams(next);
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">{isAgent ? "All tickets" : "My tickets"}</h1>
        <Link to="/tickets/new" className="btn-primary">
          New ticket
        </Link>
      </div>

      <div className="card grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
        <input
          className="input lg:col-span-2"
          type="search"
          placeholder="Search title and description…"
          aria-label="Search tickets"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <Select
          label="Status"
          value={filters.status}
          onChange={(v) => setFilter("status", v)}
          options={STATUSES.map((s) => [s, STATUS_LABELS[s]])}
        />
        <Select
          label="Priority"
          value={filters.priority}
          onChange={(v) => setFilter("priority", v)}
          options={PRIORITIES.map((p) => [p, PRIORITY_LABELS[p]])}
        />
        <Select
          label="Category"
          value={filters.category}
          onChange={(v) => setFilter("category", v)}
          options={CATEGORIES.map((c) => [c, CATEGORY_LABELS[c]])}
        />
        {isAgent && (
          <Select
            label="Assigned"
            value={filters.assigned}
            onChange={(v) => setFilter("assigned", v)}
            options={[
              ["me", "Assigned to me"],
              ["unassigned", "Unassigned"],
            ]}
          />
        )}
      </div>

      <ErrorBanner error={query.error} />
      {query.isPending ? (
        <Spinner />
      ) : (
        <div className="card overflow-x-auto p-0">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-2">Ticket</th>
                <th className="px-4 py-2">Status</th>
                <th className="px-4 py-2">Priority</th>
                <th className="px-4 py-2">Category</th>
                {isAgent && <th className="px-4 py-2">Created by</th>}
                <th className="px-4 py-2">Assignee</th>
                <th className="px-4 py-2">Updated</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {query.data.items.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-slate-500">
                    No tickets match these filters.
                  </td>
                </tr>
              )}
              {query.data.items.map((ticket) => (
                <tr key={ticket.id} className="hover:bg-slate-50">
                  <td className="px-4 py-2">
                    <Link to={`/tickets/${ticket.id}`} className="font-medium text-indigo-700 hover:underline">
                      #{ticket.id} {ticket.title}
                    </Link>
                  </td>
                  <td className="px-4 py-2"><StatusBadge status={ticket.status} /></td>
                  <td className="px-4 py-2"><PriorityBadge priority={ticket.priority} /></td>
                  <td className="px-4 py-2">{CATEGORY_LABELS[ticket.category]}</td>
                  {isAgent && <td className="px-4 py-2">{ticket.created_by.full_name}</td>}
                  <td className="px-4 py-2 text-slate-600">
                    {ticket.assigned_to?.full_name ?? "Unassigned"}
                  </td>
                  <td className="px-4 py-2 text-slate-500">{formatRelative(ticket.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex items-center justify-between text-sm text-slate-600">
        <span>
          {total} ticket{total === 1 ? "" : "s"}
        </span>
        <div className="flex items-center gap-2">
          <button type="button" className="btn-secondary" disabled={page <= 1} onClick={() => goTo(page - 1)}>
            Previous
          </button>
          <span>
            Page {page} of {lastPage}
          </span>
          <button
            type="button"
            className="btn-secondary"
            disabled={page >= lastPage}
            onClick={() => goTo(page + 1)}
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
