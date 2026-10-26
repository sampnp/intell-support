// Labels and text formatting shared by the pages.

export const STATUSES = ["open", "in_progress", "waiting_for_user", "resolved", "closed"];
export const PRIORITIES = ["low", "medium", "high", "urgent"];
export const CATEGORIES = ["account", "billing", "technical", "sync", "other"];

export const STATUS_LABELS = {
  open: "Open",
  in_progress: "In progress",
  waiting_for_user: "Waiting for user",
  resolved: "Resolved",
  closed: "Closed",
};

export const PRIORITY_LABELS = { low: "Low", medium: "Medium", high: "High", urgent: "Urgent" };

export const CATEGORY_LABELS = {
  account: "Account",
  billing: "Billing",
  technical: "Technical",
  sync: "Sync",
  other: "Other",
};

/** Button text for moving a ticket to a status (the API decides which moves are allowed). */
export const TRANSITION_LABELS = {
  in_progress: "Mark in progress",
  waiting_for_user: "Wait for user",
  resolved: "Resolve",
  closed: "Close ticket",
  open: "Reopen",
};

const dateTimeFormat = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
});
const relativeFormat = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

export function formatDateTime(iso) {
  return iso ? dateTimeFormat.format(new Date(iso)) : "";
}

export function formatRelative(iso, now = Date.now()) {
  if (!iso) return "";
  const seconds = Math.round((new Date(iso).getTime() - now) / 1000);
  const steps = [
    [60, "second"],
    [60, "minute"],
    [24, "hour"],
    [30, "day"],
    [12, "month"],
  ];
  let value = seconds;
  for (const [size, unit] of steps) {
    if (Math.abs(value) < size) return relativeFormat.format(value, unit);
    value = Math.round(value / size);
  }
  return relativeFormat.format(value, "year");
}

/**
 * What an activity event says, without the actor's name (the timeline prefixes it).
 * @param {{event_type: string, data: object}} event
 * @param {(id: number) => string} [nameFor]  looks up an agent's name for assignment events
 */
export function describeEvent(event, nameFor = (id) => `agent #${id}`) {
  const data = event.data ?? {};
  const status = (value) => STATUS_LABELS[value] ?? value;
  switch (event.event_type) {
    case "created":
      return "created the ticket";
    case "status_changed":
      return data.automatic
        ? `replied, so the status moved from ${status(data.from)} to ${status(data.to)} automatically`
        : `changed the status from ${status(data.from)} to ${status(data.to)}`;
    case "assigned":
      if (data.to_agent_id == null) return "unassigned the ticket";
      return `assigned the ticket to ${nameFor(data.to_agent_id)}`;
    case "comment_added":
      return "replied";
    case "internal_note_added":
      return "added an internal note";
    case "ticket_updated":
      return `edited the ${(data.fields ?? []).join(" and ") || "ticket"}`;
    default:
      return event.event_type;
  }
}
