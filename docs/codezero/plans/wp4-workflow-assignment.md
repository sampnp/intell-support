# WP4 — Workflow + assignment

## Context

Fourth work package from docs/PLAN.md §13. It covers:
- the ticket state machine (§6)
- `POST /tickets/{id}/status` and `POST /tickets/{id}/assign`
- moving a ticket from `waiting_for_user` back to `in_progress` when the owner comments
- `allowed_transitions` on the ticket detail

**Done when** (§13): the workflow tests are green.

It builds on WP3. WP3 already provides:
- the `status_changed` / `assigned` event types
- `get_visible_ticket`
- the `# WP4` hook in `add_comment`
- the `make_ticket(owner, status=…, assigned_to=…)` fixture

**No migration is needed.**

## Decisions

- **Unassigning is allowed.** `{"agent_id": null}` clears the assignee and writes
  `assigned {from_agent_id, to_agent_id: null}`. Rejected: making `agent_id` always required.
- **Closed tickets can't be (re)assigned.** That gives 409 `TICKET_CLOSED`, consistent with
  closed tickets refusing comments and status changes. Rejected: allowing assignment in any
  status.

Default stated to you before planning, with no objection raised:
- An agent who opened a ticket themselves gets **both** the agent transitions and the owner
  transitions (the union).

Further defaults, following the spec's "same-status transition → 409" rule:
- Assigning the current assignee again, or unassigning an unassigned ticket, gives 409
  `ASSIGNMENT_UNCHANGED`.
- An assignee that is missing or isn't an agent gives 422 `ASSIGNEE_NOT_AGENT`.

## Approach

Work happens on branch `wp4-workflow-assignment`, created before task 1.

### 1. State machine + status endpoint + auto-transition
- `app/services/workflow.py` holds the transition table, defined once as in §6:
  `TRANSITIONS: dict[TicketStatus, dict[TicketStatus, frozenset[Actor]]]`, where `Actor` is
  `"agent"` or `"owner"`.

  | From | To | Who |
  |---|---|---|
  | open | in_progress | agent |
  | open | resolved | agent |
  | in_progress | waiting_for_user | agent |
  | in_progress | resolved | agent |
  | waiting_for_user | in_progress | agent |
  | waiting_for_user | resolved | agent |
  | resolved | closed | owner, agent |
  | resolved | open | owner |
  | closed | nothing | (terminal) |

  It provides:
  - `actor_kinds(user, ticket) -> set[Actor]`: `agent` if the role is agent, `owner` if the
    user created the ticket. Both can apply.
  - `allowed_transitions(user, ticket) -> list[TicketStatus]`, in table order.
  - `change_status(db, user, ticket, to)`:
    - If `to` isn't allowed (this includes the same status), it raises
      `ConflictError("Invalid status transition", code="INVALID_TRANSITION",
      details={"from", "to", "allowed": [...]})`.
    - Otherwise it sets the status, bumps `updated_at`, and writes `status_changed {from, to}` in
      the same commit.
    - It logs `status_changed ticket_id= from= to= actor_id=`.
  - `apply_owner_comment(db, user, ticket)`: when the commenter is the owner and the status is
    `waiting_for_user`, it sets `in_progress` and adds
    `status_changed {from, to, automatic: true}`. It doesn't commit itself.
- `services/tickets.add_comment` calls `apply_owner_comment` at the `# WP4` hook, for public
  comments only. The comment, its event and the automatic status change share one commit. That
  hook comment is removed.
- `schemas/tickets.py`:
  - `StatusChange {status: TicketStatus}`.
  - `TicketOut` gains `allowed_transitions: list[TicketStatus] = []`. List items
    (`TicketSummary`) don't carry it.
- `api/tickets.py`:
  - A `_ticket_out(ticket, user)` helper fills `allowed_transitions`. Create, detail, patch,
    status and assign all return it.
  - `POST /{id}/status`: `get_visible_ticket` (someone else's ticket gives 404), then
    `change_status`, then return `TicketOut`.

### 2. Assignment
- `app/schemas/tickets.py`: `AssignRequest {agent_id: int | None}`. The key is required and may
  be null, so a missing key gives 422.
- `core/permissions.py`: `ensure_can_assign(ticket)`, where closed gives 409 `TICKET_CLOSED`.
  The agent-only rule comes from the existing `require_agent` dependency.
- `services/tickets.assign_ticket(db, agent, ticket, agent_id)` (§3 puts assignment logic here):
  - A non-null `agent_id` must be an existing user with role `agent`, otherwise 422
    `ValidationFailedError(code="ASSIGNEE_NOT_AGENT")`.
  - The same value as the current one gives 409 `ASSIGNMENT_UNCHANGED`.
  - Otherwise it sets `assigned_to`, bumps `updated_at`, and writes
    `assigned {from_agent_id, to_agent_id}` in one commit.
  - It logs `ticket_assigned`.
- `api/tickets.py`: `POST /{id}/assign` depends on `require_agent` (a user gets 403
  `AGENT_REQUIRED`), then `get_visible_ticket`, `ensure_can_assign` and `assign_ticket`, and
  returns `TicketOut`.

### 3. Tests
- `tests/test_workflow.py`:
  - **Every valid transition** (parametrized from an explicit expected list, not from
    `TRANSITIONS`, so the table itself is under test):
    - 200 with the new status
    - a `status_changed {from, to}` event by that actor
    - `updated_at` bumped
    - `allowed_transitions` in the response matches the new state
  - **Every invalid transition** (full matrix of 5 statuses × 5 targets × {owner user, agent},
    minus the valid ones, including same-status):
    - 409 `INVALID_TRANSITION`, with `details.allowed` equal to the expected list for that actor
    - status unchanged and no event written
  - **Closed is terminal:** `allowed_transitions == []` for both roles.
  - **`allowed_transitions` on `GET` detail** for owner, agent, and an agent who owns the ticket
    (the union), in every status.
  - **Auto-transition:**
    - The owner commenting on a `waiting_for_user` ticket moves it to `in_progress`. The events
      are `comment_added` then `status_changed {…, automatic: true}`.
    - An agent's public comment or internal note on `waiting_for_user` changes nothing.
    - The owner commenting on `in_progress` or `resolved` changes nothing.
  - **Validation:** an unknown status value gives 422.
- `tests/test_assignment.py`:
  - Assign: the event is `{from_agent_id: null, to_agent_id: A}`.
  - Reassign: the event is `{A → B}`.
  - Unassign with null: `assigned_to` becomes null and the event is `{A → null}`.
  - An assigned ticket then shows up in `?assigned=me`.
  - A user gets 403 `AGENT_REQUIRED`, even on their own ticket.
  - An assignee who is a `user`, or an id that doesn't exist, gives 422 `ASSIGNEE_NOT_AGENT`.
  - A closed ticket gives 409 `TICKET_CLOSED`.
  - The same assignee, or null on an unassigned ticket, gives 409 `ASSIGNMENT_UNCHANGED`.
  - A missing `agent_id` key gives 422.
  - An unknown ticket for an agent gives 404.
- `tests/test_ticket_permissions.py`:
  - Add `POST /status` to the "someone else's ticket is indistinguishable from missing" matrix.
  - Add `/status` and `/assign` to the no-token 401 matrix.

### 4. Definition of done (CLAUDE.md)
1. Copy this plan to `docs/codezero/plans/wp4-workflow-assignment.md`.
2. Mutation check: break three rules one at a time, confirm the tests fail, then revert.
   - Let the owner resolve their own open ticket.
   - Skip the auto-transition.
   - Accept a non-agent assignee.
3. Append a WP4 entry to `docs/CODEZERO_NOTES.md`.
4. `docker compose run --rm backend pytest -q` must pass before committing.
5. Commit `WP4: …` on the branch, including `.code0/`. **No AI attribution lines.**
6. Merge into `main` with `--no-ff` and push both branches.
7. **New, to stop the code0 WIP trailer coming back:**
   - Before pushing, check `git log origin/main..main` for commits I didn't make.
   - After marking the last task complete, commit the leftover `.code0` checkbox change as
     `Mark WP4 CodeZero tasks complete` and push `main`, so the tree is clean before the next
     plan runs.

## Risks

- **This plan runs after the trailer-fix plan,** which rewrites the unpushed local `main`.
  Build only starts once that has been pushed. If `main` isn't equal to `origin/main` at that
  point, I'll stop and report rather than branch from it.
- **Out of scope:** suggestions (WP6), and the dashboard and `/users/agents` (WP7). There's no
  priority or category editing, since the spec has none.

## Verification

1. `docker compose run --rm backend pytest -q` should pass everything: the earlier 116 plus the
   new workflow, assignment and permission tests.
2. `docker compose up -d backend`, then once it's up
   `curl.exe -s http://localhost:8000/api/health` should report `ok`.
3. By hand in `/docs`:
   - As an agent, assign a ticket, move it `in_progress` → `waiting_for_user`.
   - As the owner, comment, and see it return to `in_progress`.
   - Resolve it as the agent, then close it as the owner. Every response's
     `allowed_transitions` should match the table.
