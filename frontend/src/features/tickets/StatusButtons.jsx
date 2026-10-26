import { TRANSITION_LABELS } from "../../lib/format";

/**
 * One button per status the API says this user may move the ticket to (`allowed_transitions`).
 * The same component gives agents their workflow buttons and owners their Close / Reopen.
 */
export default function StatusButtons({ allowed = [], onChange, disabled = false }) {
  if (allowed.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {allowed.map((status) => (
        <button
          key={status}
          type="button"
          className={status === "resolved" ? "btn-primary" : "btn-secondary"}
          disabled={disabled}
          onClick={() => onChange(status)}
        >
          {TRANSITION_LABELS[status] ?? status}
        </button>
      ))}
    </div>
  );
}
