import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { dashboard } from "../api/endpoints";
import { ErrorBanner, PriorityBadge, Spinner, StatusBadge } from "../components/ui";
import { formatRelative } from "../lib/format";

const CARDS = [
  ["my_open", "My open tickets", "Assigned to you and not resolved"],
  ["unassigned", "Unassigned", "Active tickets nobody owns"],
  ["waiting_for_user", "Waiting for user", "Across the team"],
  ["urgent", "Urgent", "Active urgent tickets"],
];

function Queue({ title, tickets, empty }) {
  return (
    <section className="card space-y-2">
      <h2 className="font-semibold">{title}</h2>
      {tickets.length === 0 ? (
        <p className="text-sm text-slate-500">{empty}</p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {tickets.map((ticket) => (
            <li key={ticket.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
              <Link to={`/tickets/${ticket.id}`} className="flex-1 font-medium text-indigo-700 hover:underline">
                #{ticket.id} {ticket.title}
              </Link>
              <PriorityBadge priority={ticket.priority} />
              <StatusBadge status={ticket.status} />
              <span className="w-24 text-right text-xs text-slate-500">
                {formatRelative(ticket.updated_at)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default function DashboardPage() {
  const query = useQuery({ queryKey: ["dashboard"], queryFn: dashboard.agent });

  if (query.isPending) return <Spinner />;
  if (query.error) return <ErrorBanner error={query.error} />;
  const { counts, my_queue: myQueue, unassigned } = query.data;

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Dashboard</h1>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {CARDS.map(([key, label, hint]) => (
          <div key={key} className="card">
            <div className="text-sm text-slate-500">{label}</div>
            <div className={`text-3xl font-semibold ${key === "urgent" && counts.urgent ? "text-red-700" : ""}`}>
              {counts[key]}
            </div>
            <div className="text-xs text-slate-400">{hint}</div>
          </div>
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Queue title="My queue" tickets={myQueue} empty="Nothing assigned to you right now." />
        <Queue title="Unassigned" tickets={unassigned} empty="Every active ticket has an owner." />
      </div>
    </div>
  );
}
