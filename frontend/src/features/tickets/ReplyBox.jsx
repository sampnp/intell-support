import { ErrorBanner } from "../../components/ui";

/** Controlled by the page so "Insert into reply" can append passages to the text. */
export default function ReplyBox({
  value,
  onChange,
  internal,
  onInternalChange,
  onSubmit,
  canWriteInternal,
  closed,
  submitting,
  error,
}) {
  if (closed) {
    return (
      <p className="rounded-md bg-slate-100 px-3 py-2 text-sm text-slate-600">
        This ticket is closed, so it can't take new replies.
      </p>
    );
  }

  function handleSubmit(event) {
    event.preventDefault();
    if (value.trim()) onSubmit();
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2">
      <ErrorBanner error={error} />
      <label className="label" htmlFor="reply">
        {internal ? "Internal note (only agents can see this)" : "Reply"}
      </label>
      <textarea
        id="reply"
        className={`input min-h-32 ${internal ? "border-amber-400 bg-amber-50" : ""}`}
        maxLength={5000}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      <div className="flex flex-wrap items-center justify-between gap-2">
        {canWriteInternal ? (
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={internal}
              onChange={(e) => onInternalChange(e.target.checked)}
            />
            Internal note
          </label>
        ) : (
          <span />
        )}
        <button type="submit" className="btn-primary" disabled={submitting || !value.trim()}>
          {submitting ? "Sending…" : internal ? "Add note" : "Send reply"}
        </button>
      </div>
    </form>
  );
}
