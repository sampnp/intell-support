import { describe, expect, it } from "vitest";

import { describeEvent } from "./format";

const event = (event_type, data = {}) => ({ event_type, data });
const names = { 3: "Priya Shah" };
const nameFor = (id) => names[id] ?? `agent #${id}`;

describe("describeEvent", () => {
  it.each([
    [event("created"), "created the ticket"],
    [
      event("status_changed", { from: "open", to: "in_progress" }),
      "changed the status from Open to In progress",
    ],
    [
      event("status_changed", { from: "waiting_for_user", to: "in_progress", automatic: true }),
      "replied, so the status moved from Waiting for user to In progress automatically",
    ],
    [event("assigned", { from_agent_id: null, to_agent_id: 3 }), "assigned the ticket to Priya Shah"],
    [event("assigned", { from_agent_id: 3, to_agent_id: 7 }), "assigned the ticket to agent #7"],
    [event("assigned", { from_agent_id: 3, to_agent_id: null }), "unassigned the ticket"],
    [event("comment_added", { comment_id: 1 }), "replied"],
    [event("internal_note_added", { comment_id: 2 }), "added an internal note"],
    [event("ticket_updated", { fields: ["title", "description"] }), "edited the title and description"],
  ])("%j", (input, expected) => {
    expect(describeEvent(input, nameFor)).toBe(expected);
  });
});
