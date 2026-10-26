import { ErrorBanner, ModeBadge, Spinner } from "../../components/ui";
import { formatRelative } from "../../lib/format";

/** The text "Insert into reply" adds: the passage plus where it came from. */
export function suggestionQuote(hit) {
  const page = hit.page ? `, p. ${hit.page}` : "";
  return `${hit.snippet}\n\n(Source: ${hit.document_title}${page})`;
}

/**
 * Suggested KB passages for a ticket (an extractive snapshot taken at creation / on refresh).
 * `canInsert` is true for agents only: they can paste a passage into their reply.
 */
export default function SuggestionsPanel({
  suggestions,
  loading = false,
  error = null,
  canInsert = false,
  onInsert,
  onRefresh,
  refreshing = false,
}) {
  return (
    <section className="card space-y-3" aria-labelledby="suggestions-heading">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="suggestions-heading" className="font-semibold">
          Suggested solutions
        </h2>
        <div className="flex items-center gap-2">
          <ModeBadge mode={suggestions?.mode} />
          <button type="button" className="btn-secondary" onClick={onRefresh} disabled={refreshing}>
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </div>

      <ErrorBanner error={error} />
      {loading && <Spinner label="Loading suggestions…" />}

      {suggestions && suggestions.insufficient && (
        <p className="rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-600">
          {suggestions.mode
            ? "Not enough information in the knowledge base to suggest a solution."
            : "Suggestions are not available right now. Try refreshing."}
        </p>
      )}

      {suggestions && !suggestions.insufficient && (
        <ol className="space-y-3">
          {suggestions.results.map((hit) => (
            <li key={hit.chunk_id} className="rounded-md border border-slate-200 p-3">
              <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2 text-sm">
                <span className="font-medium text-slate-800">
                  {hit.document_title}
                  {hit.page ? <span className="text-slate-500">, p. {hit.page}</span> : null}
                </span>
                <span className="text-xs text-slate-500">score {hit.score.toFixed(2)}</span>
              </div>
              <p className="line-clamp-6 whitespace-pre-line text-sm text-slate-700">{hit.snippet}</p>
              {canInsert && (
                <button
                  type="button"
                  className="btn-secondary mt-2"
                  onClick={() => onInsert(suggestionQuote(hit))}
                >
                  Insert into reply
                </button>
              )}
            </li>
          ))}
        </ol>
      )}

      {suggestions?.updated_at && (
        <p className="text-xs text-slate-400">Updated {formatRelative(suggestions.updated_at)}</p>
      )}
    </section>
  );
}
