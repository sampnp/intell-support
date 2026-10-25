# WP3 — Tickets core

## Context

Third work package from docs/PLAN.md §13. It covers:
- the tickets, comments and events models plus their migration
- create, list, detail and edit for tickets
- comments, events, list filters and full-text search
- the permission rules from §7

**Done when** (§13): the ticket and permission tests are green.

It builds on WP2 (`8d03ce7`), reusing:
- `get_current_user` and `Role` for auth
- the `make_user` / `user` / `agent` / `auth_headers` test fixtures
- the `AppError` envelope
- the naming convention, and the check-constraint style used for `users.role`

**Not in WP3** (WP4 owns them):
- the state machine and `POST /status`
- `POST /assign`
- auto-moving `waiting_for_user → in_progress` when the owner comments
- `allowed_transitions`

Suggestions are WP6. WP3 leaves a clearly marked hook in `create_ticket` for them.

## Decisions

- **Closed tickets take no comments.** Commenting on a `closed` ticket gives 409 `TICKET_CLOSED`.
  `resolved` tickets still accept comments. Rejected: allowing comments in any status.
- **The user picks priority when creating a ticket**, default `medium`. It isn't editable
  afterwards in WP3: §7 only lets owners edit title and description. Rejected: always `medium`.

Defaults stated to you before planning, with no objection raised:
- **List order:** most recently updated first. With `q`, by search rank, then most recently
  updated.
- **Pagination:** `{items, total, page, page_size}`, `page_size` default 20 and max 100.
- **Ticket bodies:** include `created_by` / `assigned_to` as `{id, full_name, role}`.
- **Edit rules:** an agent PATCHing gets 403. The owner PATCHing a ticket that isn't `open` gets
  409. Someone else's ticket gets 404.
- **Comments bump `updated_at`.**
- **`ticket_events` is append-only** in the database: a trigger rejects UPDATE and DELETE.

## Approach

Work happens on branch `wp3-tickets-core`, created before task 1.

### 1. Models + migration 0002
- `app/models/ticket.py`:
  - **Enums:** `TicketStatus`, `TicketCategory`, `TicketPriority` and `EventType` as StrEnums
    with the values from §5. They are stored as strings with CHECK constraints, like
    `users.role`. `EventType` already includes WP4's `status_changed` / `assigned`, so WP4
    needs no constraint migration.
  - **`Ticket`** columns:
    - `id`
    - `title` String(200)
    - `description` Text
    - `category`
    - `priority` (default `medium`)
    - `status` (default `open`)
    - `created_by` FK users, indexed
    - `assigned_to` FK users, nullable, indexed
    - `created_at` / `updated_at` timestamptz, `server_default now()`
    - `search_vector` TSVECTOR as a `Computed(..., persisted=True)` stored generated column.
      Title is weighted A and description B, with the `english` config, plus a GIN index. Being
      generated, it can never drift from the text.

    It also has an index on `status`. Relationships are `creator` and `assignee`.
  - **`TicketComment`** columns:
    - `id`
    - `ticket_id` FK, indexed
    - `author_id` FK
    - `body` Text
    - `is_internal` bool, default false
    - `created_at`

    Relationship: `author`.
  - **`TicketEvent`** columns:
    - `id`
    - `ticket_id` FK, indexed
    - `actor_id` FK
    - `event_type` (CHECK)
    - `data` JSONB, default `{}`
    - `created_at`

    Relationship: `actor`.
  - `INTERNAL_EVENT_TYPES = {internal_note_added}` is the single definition of which events
    users never see.
  - The models are registered in `app/models/__init__.py`.
- `alembic/versions/0002_create_tickets.py` (down_revision `0001`) creates:
  - the three tables, their constraints and indexes, and the GIN index
  - a `ticket_events_append_only()` PL/pgSQL function, and a `BEFORE UPDATE OR DELETE` trigger
    that raises
  - a `downgrade` that drops all of it

### 2. Schemas, permissions, service
- `app/schemas/tickets.py`:
  - `UserSummary {id, full_name, role}`.
  - `TicketCreate`:
    - `title`, stripped, 5–200
    - `description`, stripped, 10–5000
    - `category` (enum)
    - `priority` (enum, default `medium`)

    Extra keys such as `status` and `assigned_to` are ignored.
  - `TicketUpdate`: optional `title` / `description` with the same rules. Explicit nulls are
    rejected, and a body with neither field gets 422.
  - `TicketOut`: every ticket field, with `created_by` / `assigned_to` read from the
    `creator` / `assignee` relationships via `validation_alias`.
  - `TicketSummary`: `TicketOut` minus `description`, for lists.
  - `TicketPage {items, total, page, page_size}`.
  - `CommentCreate`: `body`, stripped, 1–5000, and `is_internal`, default false.
  - `CommentOut {id, ticket_id, author, body, is_internal, created_at}`.
  - `EventOut {id, ticket_id, actor, event_type, data, created_at}`.
- `app/core/permissions.py` is the single place for ticket access rules (§3 / §4):
  - `is_agent(user)`.
  - `ticket_scope(stmt, user)`: users see only their own tickets (`created_by == user.id`),
    agents see all.
  - `get_visible_ticket(db, ticket_id, user)`: a missing ticket, or one the user can't see, raises
    the same `NotFoundError("Ticket not found", code="TICKET_NOT_FOUND")`, so IDs can't be
    enumerated. Hiding an existing ticket logs `permission_denied ... reason=not_owner`.
  - `ensure_can_edit(user, ticket)`:
    - agent → 403 `TICKET_EDIT_FORBIDDEN`
    - not `open` → 409 `TICKET_NOT_EDITABLE`
  - `ensure_can_comment(user, ticket, is_internal)`:
    - user posting an internal note → 403 `INTERNAL_NOTE_FORBIDDEN`
    - `closed` → 409 `TICKET_CLOSED`
  - `can_see_internal(user)`.
- `app/services/tickets.py`. Every state change and its event are written in **one commit**
  (§4).
  - `create_ticket`: the ticket plus a `created` event. A `# WP6: suggestions snapshot` hook
    point is marked here.
  - `list_tickets(db, user, filters) -> (items, total)`:
    - `ticket_scope` is applied.
    - Filters: `status`, `priority`, `category`, and `assigned=me|unassigned`.
    - `q`: a non-blank value matches with `search_vector @@ websearch_to_tsquery('english', q)`
      and is ordered by `ts_rank_cd`, then `updated_at desc, id desc`. A blank `q` is ignored.
    - The count uses the same filtered statement. `creator` / `assignee` are loaded with
      `selectinload`.
  - `update_ticket`:
    - It applies only fields whose value actually changed, sets `updated_at`, and writes
      `ticket_updated {fields: [...]}`.
    - If nothing changed, it writes no event.
  - `add_comment`:
    - It writes the comment plus a `comment_added` or `internal_note_added` event `{comment_id}`,
      and bumps the ticket's `updated_at`.
    - WP4 adds the auto-transition here.
  - `list_comments` / `list_events`: oldest first, and internal ones are filtered out for users.
  - Logs: `ticket_created`, `ticket_updated fields=`, `comment_added internal=`.
- `app/api/tickets.py`, included in `main.py`. All endpoints require `get_current_user`.
  - `POST /tickets` → 201 `TicketOut`
  - `GET /tickets` → `TicketPage`. Query params are validated: enum filters,
    `assigned: Literal["me","unassigned"]`, `page ≥ 1`, `1 ≤ page_size ≤ 100` and `q` of at most
    200 chars.
  - `GET /tickets/{id}` → `TicketOut`
  - `PATCH /tickets/{id}` → `TicketOut`
  - `GET /tickets/{id}/comments` → `list[CommentOut]`
  - `POST /tickets/{id}/comments` → 201 `CommentOut`
  - `GET /tickets/{id}/events` → `list[EventOut]`

### 3. Tests
- `tests/conftest.py`: a `make_ticket(owner, **fields)` fixture creates a ticket through the
  service, so it has its `created` event. WP4 reuses it.
- `tests/test_tickets.py`:
  - **Create:**
    - 201, `open`, priority defaults to `medium`, a chosen priority is honoured,
      `status`/`assigned_to` in the body are ignored, and the `created` event is written.
    - 422 for title too short or too long, description too short, bad category and bad priority.
    - Whitespace is stripped.
  - **Detail:** the owner and any agent can read a ticket. An unknown id gives 404
    `TICKET_NOT_FOUND`.
  - **List:**
    - A user sees only their own tickets and an agent sees all of them.
    - Each filter works, including `assigned=me` / `unassigned`.
    - `q` matches title and description, with stemming (`syncing` finds "sync"). A nonsense `q`
      returns an empty list.
    - Pagination `total` and `page_size` are correct, and `page_size=101` gives 422.
    - The most recently updated ticket comes first.
  - **Patch:**
    - The owner editing an open ticket gets 200 and a `ticket_updated` event with the right
      `fields`.
    - An empty body gives 422, an agent gets 403, and a non-open ticket gives 409.
    - An unchanged value writes no event.
- `tests/test_comments_events.py`:
  - **Comments:**
    - A user comments on their own ticket and an agent posts a public comment: both write
      `comment_added` and bump `updated_at`.
    - An agent's internal note writes `internal_note_added`. A user's internal note gets 403.
    - A closed ticket gives 409 `TICKET_CLOSED`. A resolved ticket is OK.
    - An empty body gives 422.
  - **Visibility:**
    - A user's comment list and event list contain no internal notes or `internal_note_added`
      events.
    - An agent's lists contain both.
    - Lists come back oldest first.
  - **Append-only:** an UPDATE and a DELETE on `ticket_events` both raise a database error.
    Each runs inside `begin_nested()` so the test transaction survives.
- `tests/test_ticket_permissions.py`:
  - User A on user B's ticket gets 404 `TICKET_NOT_FOUND` on detail, patch, both comments
    endpoints and events. The response body is identical to a nonexistent id's, and a
    `permission_denied` line is logged.
  - Every ticket endpoint without a token gets 401 (parametrized).

### 4. Definition of done (CLAUDE.md)
1. Copy this plan to `docs/codezero/plans/wp3-tickets-core.md`.
2. Mutation check, as in WP1/WP2: break three rules one at a time, confirm the tests fail, then
   revert.
   - Drop `ticket_scope`'s owner filter.
   - Return internal comments to users.
   - Let users post internal notes.
3. Append a WP3 entry to `docs/CODEZERO_NOTES.md`.
4. `docker compose run --rm backend pytest -q` must pass before committing.
5. Commit `WP3: tickets core (...)` on `wp3-tickets-core`, including `.code0/`. **No AI
   attribution lines.**
6. Merge into `main` with `--no-ff` and push both branches.

## Risks

- **Clock source for `updated_at`.** It's set from Python on update, while `created_at` /
  `updated_at` defaults come from Postgres `now()`, which is the transaction start time. Tests
  run inside one transaction, so every ticket created in a test shares a timestamp. The ordering
  test relies on an updated ticket getting a later Python time, and every ordering has an `id`
  tiebreak.
- **The append-only trigger also blocks deleting events through a cascade.** No endpoint deletes
  tickets, so nothing is affected today. A future ticket delete would have to drop the trigger
  or archive.
- **Out of scope:** status changes, assignment, `allowed_transitions` and auto-transition (all
  WP4); suggestions (WP6); the dashboard and `/users/agents` (WP7).

## Verification

1. `docker compose run --rm backend pytest -q` should pass all tests: WP1, WP2 and the new WP3
   tests.
2. `docker compose up -d backend` runs migration 0002 on start. Once the server is up (allow a
   few seconds for the `--reload` startup gap), `curl.exe -s http://localhost:8000/api/health`
   should report `ok`.
3. By hand in `/docs`: register, create a ticket, list it with `q`, add a comment, and see the
   `created` / `comment_added` events.
