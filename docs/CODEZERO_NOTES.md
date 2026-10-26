# CodeZero Development Log

How CodeZero (Frigga's VS Code extension, using Claude Code as its execution agent) was used to
build this project: planning, implementation, debugging, test generation and verification.

## Workflow

1. **Context:** the repository is connected and indexed in CodeZero; `docs/PLAN.md` is the spec
   every prompt refers to.
2. **Plan:** each work package (see PLAN.md §13) starts in **Planned mode** with
   `/plan Implement WPn as described in docs/PLAN.md`.
3. **Review:** the generated plan is read and edited before approval (changes recorded below).
4. **Execute:** approved plan runs as CodeZero Tasks. Risky logic (permissions, state machine,
   retrieval fallback) is confirmed step by step; boilerplate may use Coffee Mode.
5. **Verify:** pytest / Playwright run after each WP; the diff is reviewed manually. For core rules
   the logic is deliberately broken once to confirm the tests actually catch it.
6. **Debug:** failures are investigated with CodeZero Chat / Flow Trace.
7. **Commit:** reviewed changes are committed with a summary from the Git Tree.


---

## Log

### WP0 — Repository skeleton   (2026-10-26)
- Mode: n/a — written before the repository existed in CodeZero (CodeZero indexes repos from
  GitHub, so the skeleton had to be pushed first).
- What was created: `.gitignore`, `.gitattributes`, `.env.example`, `docker-compose.yml`
  (postgres + qdrant), test-database init script, `docs/PLAN.md`, this log, README stub.
- Next: connect GitHub in CodeZero, index the repo, start WP1 in Planned mode.


### WP1 — Backend foundation   (2026-10-26)
- Mode: Planned → Run phase (5 tasks)
- Setup challenge: CodeZero could not launch Claude on Windows ("Native CLI binary for win32-x64
  not found"). Found the cause in the CodeZero output log; set code0.providerPaths.claude to the
  native claude.exe (the npm .cmd wrapper can't be spawned by the SDK).
- Decision asked by CodeZero: embedder status in /api/health before WP6 exists → chose placeholder
  "not_configured" to keep WP1 scoped and builds fast. (CodeZero caught this gap in my spec.)
- Departures from the plan (accepted): log-record factory instead of filter (so pytest caplog sees
  request ids); uvicorn access log off (middleware logs requests); CORS credentials off (bearer auth);
  extra 405 test.
- Verification: compose up, /api/health returns ok, 20 tests pass in Docker. Mutation check: made
  the 500 handler leak the message, made health ignore Qdrant errors, accepted invalid request ids;
  1, 2 and 3 tests failed respectively, so the suite catches real defects.
- Follow-up for WP6: use a shared Qdrant client instead of one per request.


### WP2 — Users + auth   (2026-10-26)
- Mode: Planned → Run phase (5 tasks)
- Prompt: "okay so we have finished w1 lets continue with w2"
- Plan summary: users table + migration 0001, register/login/me under /api/auth, bcrypt hashing,
  JWT (sub/iat/exp only, role read from DB each request), `get_current_user` / `require_agent`,
  shared test fixtures (`make_user`, `user`, `agent`, `auth_headers`) for later WPs.
- Decisions asked by CodeZero: register response → token + user (same as login, so the frontend
  has one code path); login body → JSON `{email, password}` rather than the OAuth2 form.
  It also flagged choices I hadn't specified: bcrypt's 72-byte limit (now a clean 422 instead of a
  500), FastAPI's HTTPBearer answering a missing token with 403 instead of 401, passlib being
  unmaintained, and email-validator rejecting `.test`/`.local` addresses (matters for WP7 seeds).
- What was generated: `core/security.py`, `core/deps.py`, `models/user.py`, migration 0001,
  `schemas/auth.py`, `services/auth.py`, `api/auth.py`, `UnauthorizedError` (with
  `WWW-Authenticate: Bearer`), 31 new tests.
- Departure from the plan: HTTPBearer returns nothing for a `Basic` header, so `get_current_user`
  checks the raw Authorization header to answer `INVALID_TOKEN` instead of `NOT_AUTHENTICATED`.
- Verification: 51 tests pass in Docker (20 WP1 + 31 new). Mutation check: let users through
  `require_agent`, disabled expiry checking, let register honour `role` from the body → 1, 2 and
  1 tests failed respectively; all reverted.
- Screenshots:
- Time taken:


### WP3 — Tickets core   (2026-10-26)
- Mode: Planned → Run phase (4 tasks)
- Prompt: "no no continue with w3 only" (after asking whether WP3–WP8 could be done in one go;
  CodeZero recommended one plan per WP so each stays reviewable and gets its own log entry)
- Plan summary: tickets / ticket_comments / ticket_events models + migration 0002; create, list
  (filters, full-text search, pagination), detail, edit; comments with internal notes; events;
  all access rules in `core/permissions.py`.
- Decisions asked by CodeZero: comments on closed tickets → refused with 409 (closed is terminal);
  priority → chosen by the user at creation, default medium. Defaults it stated and I accepted:
  most-recently-updated ordering (rank first when searching), `{items, total, page, page_size}`,
  agents get 403 on edit, comments bump `updated_at`, events append-only enforced by a DB trigger.
- What was generated: models with a generated `search_vector` column (title weighted above
  description, GIN index), migration 0002 with the append-only trigger, `core/permissions.py`,
  `services/tickets.py`, 7 endpoints, `make_ticket` fixture, 65 new tests. WP4/WP6 hook points
  are marked in the service.
- Issues found: none failed on the first run, which is why the mutation check matters here.
  Before pushing, CodeZero noticed an unpushed commit it hadn't made: the extension had
  auto-committed WP2's leftover task checkbox when the WP3 plan ran, with a
  `Co-authored-by: Code-Zero` trailer (against CLAUDE.md). It held the push; a small follow-up
  plan re-applied that change without the trailer, cherry-picked WP3 on top (diff against the
  tested merge: empty) and pushed. From WP4 on, the leftover checkbox is committed by hand at the
  end of each WP so the next Run has nothing to auto-commit.
- Verification: 116 tests pass in Docker (51 earlier + 65 new). Mutation check: users see all
  tickets in the list, internal notes returned to users, users allowed to post internal notes →
  1 test failed each; all reverted.
- Screenshots:
- Time taken:


### WP4 — Workflow + assignment   (2026-10-26)
- Mode: Planned → Run phase (4 tasks)
- Prompt: "Remove the trailer first  w4 continue"
- Plan summary: transition table in `services/workflow.py` (defined once, as in §6), status
  endpoint with 409 + `details.allowed`, automatic `waiting_for_user → in_progress` when the
  owner replies, `allowed_transitions` on every ticket response, assign/reassign/unassign endpoint.
- Decisions asked by CodeZero: unassigning allowed (`agent_id: null`); closed tickets can't be
  assigned (409). Defaults it stated: an agent who opened a ticket gets both agent and owner
  moves; re-assigning the same agent → 409 `ASSIGNMENT_UNCHANGED`; non-agent assignee → 422.
- What was generated: `services/workflow.py`, `services/events.py`, status + assign endpoints,
  90 new tests. The tests write the expected transition table out independently of the code and
  check the full 5×5 matrix for both roles (9 valid, 41 invalid), so a wrong table entry fails.
- Departure from the plan: `services/events.py` (shared `add_event` / `utcnow`) was added so
  `tickets.py` and `workflow.py` don't import each other.
- Also in this commit: my own edit to PLAN.md §13 (WP12 no longer includes screenshots/video).
  CodeZero spotted the uncommitted change it hadn't made and asked before including it.
- Verification: 206 tests pass in Docker (116 earlier + 90 new). Mutation check: owner allowed
  to resolve an open ticket → 7 failed; auto-transition skipped → 2 failed; non-agent assignee
  accepted → 1 failed; all reverted.
- Screenshots:
- Time taken:


### WP5 — KB ingestion   (2026-10-26)
- Mode: Planned → Run phase (6 tasks)
- Prompt: "w5"
- Plan summary: documents + document_chunks (UUID ids for Qdrant, generated `tsv` + GIN index),
  upload validation (415/413/400 before anything is stored), PDF/TXT extraction with page
  numbers, paragraph-aware chunking (~800 chars, ~150 overlap, never across pages), background
  processing that always ends `ready` or `failed`, agent-only list/detail/delete, Acme Cloud
  sample KB + malformed fixtures. Embeddings/Qdrant deliberately left to WP6.
- Decisions asked by CodeZero: sample PDFs built by a generator script (fpdf2) with content it
  writes; document list/detail agents only; same filename may be uploaded twice. It also flagged
  that `.gitattributes`' `text=auto` could rewrite the bytes of the deliberately broken fixtures,
  and marked `sample_kb/malformed/*` binary.
- What was generated: `services/chunking.py`, `services/ingestion.py`, `api/kb.py`, migration
  0003, three TXT docs, `scripts/build_sample_kb.py` (3 PDFs + corrupt / image-only /
  binary-garbage fixtures), 42 new tests. Background tasks get their own DB session through an
  overridable dependency, so tests run them inside the rolled-back test transaction.
- Verification: generated guide PDF checked visually (3 pages, real text layer). 248 tests pass in
  Docker (206 earlier + 42 new). Mutation check: chunks allowed to span pages → 4 failed; `%PDF`
  check skipped → 1 failed; image-only PDF marked ready → 1 failed; all reverted.
- Screenshots:
- Time taken:


### WP6 — Retrieval   (2026-10-26)
- Mode: Planned → Run phase (6 tasks)
- Prompt: "okay w6"
- Plan summary: fastembed `bge-small-en-v1.5` baked into the image, shared Qdrant client +
  `kb_chunks` wrapper, keyword search over `document_chunks.tsv`, semantic-first retrieval with
  keyword fallback and a score threshold, `/api/kb/search`, indexing on ingest, reindex, delete
  from both stores, and a suggestions snapshot on ticket creation with refresh.
- Decisions asked by CodeZero: snapshot mode + time stored on the ticket (two nullable columns,
  so an empty snapshot still says which mode ran); explicit `mode=semantic` with Qdrant/model
  down → 503 instead of a silent fallback.
- Decision raised during the build: a test showed that keyword search with "all words must
  match" (`websearch_to_tsquery`, as in the spec) almost never matches a whole ticket's title +
  description, so fallback suggestions would always be empty. CodeZero stopped and asked instead
  of changing the spec on its own; chose "all words first, then any word, ranked".
- Issue found and fixed: until the test overrides existed, two test runs used the real model and
  wrote test points into the dev Qdrant collection (harmless orphans: search joins back to
  Postgres). The overrides were moved forward so tests never touch the real Qdrant again.
- What was generated: `services/embeddings.py`, `vector_store.py` (rewritten),
  `keyword_search.py`, `retrieval.py`, `suggestions.py`, migration 0004, search / reindex /
  suggestions endpoints, a deterministic hashing fake embedder, 63 new tests incl. one slow test
  with the real model (4 natural-language queries hit their document in the top 3 at 0.5).
- Also in this commit: my replan of PLAN.md §13 (WP7–WP12 folded into WP7–WP10; eval script a
  stretch goal; one Playwright smoke spec; no live suggestions while typing). CodeZero spotted
  the uncommitted edit before committing and asked whether to include it.
- Verification: 312 tests pass in Docker (249 earlier + 63 new). Mutation check: `auto` doesn't
  fall back → 3 failed; threshold not applied → 2 failed; ticket creation unprotected from
  retrieval errors → 1 failed; all reverted.
- Screenshots:
- Time taken:


### WP7 — Backend wrap-up   (2026-10-26)
- Mode: Planned → Run phase (4 tasks)
- Prompt: "w7"
- Plan summary: `scripts/seed.py` (2 agents, 2 users, sample KB indexed, 8 tickets covering every
  status built through the real services), `GET /api/dashboard/agent`, `GET /api/users/agents`.
- Decisions asked by CodeZero: a plain seed run skips when already seeded and `--reset` wipes and
  reseeds; verification may reset the dev DB (also clears WP6's orphan Qdrant points);
  "waiting for user" and "urgent" cards count the whole team, "my open" is personal.
- Issue: code0 auto-committed my uncommitted PLAN.md replan with its `Co-authored-by: Code-Zero`
  trailer when I pressed Run, and on later Runs moved `main` back and made more auto-commits on
  its own branches. CodeZero stopped before building, a small fix plan re-committed the replan,
  and when code0 undid that too, CodeZero branched WP7 from the clean `main` and re-applied my
  replan as file edits (diff against code0's commit: empty). So the replan is part of this
  commit, and no trailer commit is an ancestor of `main`. Lesson: commit my own edits before
  pressing Run.
- What was generated: `services/dashboard.py`, dashboard + users routers, `scripts/seed.py`,
  `VectorStore.drop_collection`, 13 new tests.
- Mutation check found a gap: counting resolved tickets as "unassigned" passed all tests (no test
  had an unassigned *resolved* ticket). Added one; now it fails. Agents list returning users →
  1 failed; no already-seeded check → 1 failed; all reverted.
- Verification: 325 tests pass in Docker (312 earlier + 13 new); dev stack seeded with `--reset`
  and a plain re-run reports "already seeded".
- Screenshots:
- Time taken:


---

## Summary (written at the end)

- Where CodeZero helped most:
- Where its output was wrong or needed correction:
- How generated code was verified:
- What I would do differently:
