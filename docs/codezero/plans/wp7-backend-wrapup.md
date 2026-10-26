# WP7 — Backend wrap-up: seed script, agent dashboard, agents list

## Context

This is WP7 of the replanned docs/PLAN.md §13. It covers:
- a seed script: 2 agents, 2 users, the sample KB ingested, and about 8 tickets across all
  statuses with comments and internal notes, on `@acme-demo.com` emails
- `GET /api/dashboard/agent`: counts, my queue and unassigned (§8, §11.5)
- `GET /api/users/agents`: for the assignment dropdown

**Done when:** the seeded demo works and the tests are green. It's the last backend package
before the frontend (WP8). The seed gives WP8 and the README a realistic, repeatable demo state.

## Decisions

- **Re-running the seed:** a plain run **skips** when the demo data is already there, so it never
  creates duplicates. `--reset` truncates every table and recreates the Qdrant collection, then
  seeds. Rejected: always wiping, and refusing on a non-empty database.
- **Verification runs `--reset` on the dev database,** with your approval. That gives a clean
  demo state and also clears the orphan test points WP6 left in the dev Qdrant. Anything created
  by hand in the dev database is lost.
- **The "waiting for user" and "urgent" cards count the whole team's active tickets.** "My open"
  is the personal card. Active means `open`, `in_progress` or `waiting_for_user`. Rejected: only
  the agent's own tickets.

Defaults stated to you before planning, with no objection raised:
- **Seed password:** taken from `SEED_PASSWORD`, defaulting to `demo-password`. It's printed at
  the end of the run.
- **How the seed is built:** the KB is ingested with the real embedder. Tickets are created
  through the real services (create with suggestions, assign, status changes, comments), so their
  events and suggestions are genuine.
- **Queues:** each queue is ordered urgent, then high, medium, low, then most recently updated,
  and shows at most 20 tickets. The counts aren't capped.
- **`/api/users/agents`:** agents only. It returns `[{id, full_name, role}]` sorted by name.
- **Your uncommitted `docs/PLAN.md` edit** (WP8 = whole frontend, WP9 = delivery, Playwright as a
  stretch goal) goes into the WP7 commit, as for WP4 and WP6, and is noted in the log.

## Approach

Work happens on branch `wp7-backend-wrapup`, created before task 1.

### 1. Dashboard + agents endpoints
- `services/dashboard.py`:
  - `ACTIVE_STATUSES` is open, in_progress and waiting_for_user.
  - `PRIORITY_ORDER` is a SQL `case` mapping urgent=0 through low=3.
  - `agent_dashboard(db, agent, limit=20)` returns these counts:
    - `my_open`: assigned to me and active
    - `unassigned`: no assignee and active
    - `waiting_for_user`: all tickets in that status
    - `urgent`: urgent and active

    It also returns the `my_queue` and `unassigned` lists, ordered by `PRIORITY_ORDER`, then
    `updated_at desc, id desc`, with `selectinload` for creator and assignee.
- `schemas/dashboard.py`: `DashboardCounts`, and `AgentDashboard {counts, my_queue, unassigned}`.
  The two lists reuse `TicketSummary`.
- `api/dashboard.py`: `GET /api/dashboard/agent` behind `require_agent`.
- `api/users.py`: `GET /api/users/agents` behind `require_agent`, returning
  `list[UserSummary]` sorted by full name.
- Both routers are included in `main.py`.

### 2. Seed script
- `services/vector_store.py`: add `VectorStore.drop_collection()`, used by `--reset`.
- `backend/scripts/seed.py`, run with `python -m scripts.seed [--reset]` from `/app`:
  - `seed(db, embedder, store, *, sample_kb_dir, password, reset=False) -> SeedResult` holds the
    logic, so tests can call it with the fakes.
  - **Reset:** `TRUNCATE ticket_suggestions, ticket_events, ticket_comments, tickets,
    document_chunks, documents, users RESTART IDENTITY CASCADE`. TRUNCATE doesn't fire the
    append-only row trigger. Then `store.drop_collection()`.
  - **Already-seeded check:** if `priya@acme-demo.com` exists, it returns
    `SeedResult(skipped=True)` and changes nothing.
  - **Users:**
    - agents: Priya Shah and Marcus Lee
    - users: Dana Whitfield and Sam Ortiz
    - all `@acme-demo.com`, with hashed `password`
  - **KB:** every top-level file in the sample KB goes through `ingest_bytes`, with the embedder
    and store, uploaded by Priya.
  - **Tickets:** 8 tickets, created through `create_ticket(..., suggest=snapshot)`,
    `assign_ticket`, `workflow.change_status` and `add_comment`.

    | # | Ticket | Final status |
    |---|---|---|
    | 1 | Dana, charged twice (billing, high), Priya: reply, waiting, Dana replies (automatic back to in progress) | in_progress |
    | 2 | Dana, sync stuck on a large file (sync, medium) | open, unassigned |
    | 3 | Sam, locked out after failed logins (account, **urgent**) | open, unassigned |
    | 4 | Sam, share link expiry (other, low), Marcus: reply | resolved |
    | 5 | Dana, conflicted copies in a team folder (sync, medium), Priya: internal note, reply | waiting_for_user |
    | 6 | Sam, data export before cancelling (account, medium), Marcus | resolved, then **closed by Sam** |
    | 7 | Dana, 2FA codes rejected (account, high), Priya | resolved, then **reopened by Dana**, so open |
    | 8 | Sam, desktop app won't install (technical, medium), Priya: internal note | in_progress |

    Every status is covered, along with internal notes, an automatic transition, a close and a
    reopen.
  - **`main()`:**
    - It parses `--reset`, configures logging, and opens `SessionLocal()`.
    - It uses the real `get_embedder()` and `get_vector_store()`.
    - It prints a summary: the counts, each login email and role, and the password.

### 3. Tests
- `tests/test_dashboard.py`:
  - **Counts:** exact counts on a hand-built set of tickets, covering mine versus another agent's,
    unassigned, waiting, urgent, and resolved or closed excluded.
  - **Queues:** contents and order, with urgent first and then most recently updated.
  - **Limit:** with 22 unassigned tickets, the list holds 20 and the count is 22.
  - **Shape:** the list items carry no description.
  - **Access:** a user gets 403 and no token gets 401.
- `tests/test_users.py`:
  - **Contents:** agents only, sorted by name, with fields `{id, full_name, role}`.
  - **Access:** a user gets 403 and no token gets 401.
- `tests/test_seed.py` runs `seed()` with `db_session`, `HashingEmbedder`, the in-memory store and
  the sample KB:
  - **Contents:**
    - 4 users, 2 of them agents
    - 6 documents, all `ready` and `vector_indexed`
    - 8 tickets
    - the status set equals all 5 statuses
    - at least one internal note
    - an automatic `status_changed` event
    - a `closed` ticket with an owner close event
    - every ticket has a `suggestions_mode`
  - **Login:** a seeded agent can log in through `/api/auth/login` with the password and then load
    the dashboard. A seeded user gets 403 there.
  - **Second run:** it's `skipped`, and every count is unchanged.
  - **`reset=True`:** an extra hand-made user is gone, and the counts match a fresh seed.

### 4. Definition of done (CLAUDE.md)
1. Copy this plan to `docs/codezero/plans/wp7-backend-wrapup.md`.
2. Mutation check: break three rules one at a time, confirm the tests fail, then revert.
   - Count resolved tickets as unassigned.
   - Return non-agents from `/users/agents`.
   - Remove the already-seeded check.
3. Append a WP7 entry to `docs/CODEZERO_NOTES.md`.
4. `docker compose run --rm backend pytest -q` must pass before committing.
5. Seed the dev stack: `docker compose run --rm backend python -m scripts.seed --reset`, then
   run the plain command again and confirm it reports skipped.
6. Check `git log origin/main..HEAD` and `git status` for foreign changes.
7. Commit `WP7: …` including `.code0/` and your `PLAN.md` edit, with no AI attribution. Merge into
   `main` with `--no-ff` and push both branches.
8. After the last task is marked complete, commit `Mark WP7 CodeZero tasks complete` and push
   `main`.

## Risks

- **`--reset` is destructive by design.** It only runs when the flag is passed. The test suite
  only exercises it inside the rolled-back test transaction.
- **The seed loads the real model,** which takes a few seconds, so the first run is slower.
- **Out of scope:** the retrieval eval script (a stretch goal in the replan) and the frontend.

## Verification

1. `docker compose run --rm backend pytest -q` should pass everything: the earlier 312 plus the
   new dashboard, users and seed tests.
2. `docker compose run --rm backend python -m scripts.seed --reset` should print 4 users,
   6 documents and 8 tickets, plus the logins.
3. Running `docker compose run --rm backend python -m scripts.seed` again should print that it was
   already seeded and skipped.
4. `docker compose up -d backend`, then `curl.exe -s http://localhost:8000/api/health` should
   report `ok`.
5. By hand in `/docs`: log in as `priya@acme-demo.com` / `demo-password`. The dashboard should
   show non-zero counts and queues, and `/api/users/agents` should list Marcus and Priya.
