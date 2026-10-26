// Small shared presentational pieces.
import { PRIORITY_LABELS, STATUS_LABELS } from "../lib/format";

const STATUS_STYLES = {
  open: "bg-sky-100 text-sky-800",
  in_progress: "bg-indigo-100 text-indigo-800",
  waiting_for_user: "bg-amber-100 text-amber-800",
  resolved: "bg-emerald-100 text-emerald-800",
  closed: "bg-slate-200 text-slate-700",
};

const PRIORITY_STYLES = {
  low: "bg-slate-100 text-slate-700",
  medium: "bg-blue-50 text-blue-700",
  high: "bg-orange-100 text-orange-800",
  urgent: "bg-red-100 text-red-800",
};

function Pill({ className, children }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${className}`}
    >
      {children}
    </span>
  );
}

export function StatusBadge({ status }) {
  return <Pill className={STATUS_STYLES[status] ?? ""}>{STATUS_LABELS[status] ?? status}</Pill>;
}

export function PriorityBadge({ priority }) {
  return (
    <Pill className={PRIORITY_STYLES[priority] ?? ""}>{PRIORITY_LABELS[priority] ?? priority}</Pill>
  );
}

/** Which retrieval mode produced a result: semantic (vectors) or keyword (fallback). */
export function ModeBadge({ mode }) {
  if (!mode) return null;
  const semantic = mode === "semantic";
  return (
    <Pill className={semantic ? "bg-violet-100 text-violet-800" : "bg-amber-100 text-amber-800"}>
      {semantic ? "Semantic search" : "Keyword search"}
    </Pill>
  );
}

export function ErrorBanner({ error }) {
  if (!error) return null;
  return (
    <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
      {error.message ?? String(error)}
    </div>
  );
}

export function Spinner({ label = "Loading…" }) {
  return (
    <div className="flex items-center gap-2 py-6 text-sm text-slate-500" role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-indigo-600" />
      {label}
    </div>
  );
}

export function FieldError({ message }) {
  if (!message) return null;
  return <p className="mt-1 text-xs text-red-700">{message}</p>;
}
