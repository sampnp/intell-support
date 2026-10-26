# Intell-Support — Implementation Plan

This is the agreed specification for the project. Every work package (WP) below is implemented
through CodeZero (Planned mode) and must follow the conventions and decisions in this document.
When a prompt says "implement WP3", this file is the source of truth.

---

## 1. Goal

A support platform where users create tickets, agents resolve them through a structured workflow,
and every ticket is automatically matched against a knowledge base (KB) of PDF/TXT documents using
semantic search — with a keyword-search fallback so the system keeps working when the vector
store or embedding model is unavailable.

**Explicit non-goals:** no LLM / generated answers (suggestions are extractive passages with
sources), no multi-agent orchestration, no cloud services, no paid APIs.

---

## 2. Stack

| Layer | Choice |
|---|---|
| Frontend | React 18 + Vite, **JavaScript (no TypeScript)**, React Router, TanStack Query, Tailwind CSS |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (**sync** sessions), Alembic, psycopg 3 |
| Auth | JWT bearer tokens (PyJWT), passwords hashed with bcrypt |
| Database | PostgreSQL 16 (also provides full-text search for the keyword fallback) |
| Vector store | Qdrant (Docker), collection `kb_chunks`, cosine distance |
| Embeddings | `fastembed` with `BAAI/bge-small-en-v1.5` (384-dim, ONNX, CPU). Model downloaded at Docker build time |
| PDF text | `pypdf` |
| Tests | pytest (backend), Playwright (frontend e2e, JS) |
| Dev | Docker Compose: `postgres`, `qdrant`, `backend`, `frontend` |

The backend and its tests run inside Docker on Python 3.12 (the host has Python 3.14, which some
dependencies do not support yet).

---

## 3. Repository layout

```
intell-support/
├── backend/
│   ├── app/
│   │   ├── main.py              # app factory, routers, middleware, exception handlers
│   │   ├── config.py            # pydantic-settings, reads env
│   │   ├── db.py                # engine, SessionLocal, get_db dependency
│   │   ├── core/
│   │   │   ├── security.py      # hashing, JWT encode/decode
│   │   │   ├── deps.py          # get_current_user, require_agent
│   │   │   ├── permissions.py   # ticket visibility / action checks (single place)
│   │   │   ├── errors.py        # AppError hierarchy + handlers → error envelope
│   │   │   └── logging.py       # structured logging + request-id middleware
│   │   ├── models/              # SQLAlchemy models
│   │   ├── schemas/             # Pydantic request/response models
│   │   ├── api/                 # routers: auth, tickets, kb, users, dashboard, health
│   │   └── services/
│   │       ├── workflow.py      # ticket state machine
│   │       ├── tickets.py       # ticket/comment/assignment logic + event writing
│   │       ├── ingestion.py     # validate → extract → chunk → store → index
│   │       ├── chunking.py
│   │       ├── embeddings.py    # Embedder interface + FastEmbedEmbedder
│   │       ├── vector_store.py  # Qdrant wrapper
│   │       ├── keyword_search.py# Postgres full-text search over chunks
│   │       └── retrieval.py     # semantic-first, keyword fallback, threshold logic
│   ├── alembic/
│   ├── scripts/                 # seed.py (eval_retrieval.py only if time remains)
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/ (api/, pages/, components/, hooks/, context/)
│   ├── e2e/                     # Playwright smoke spec (stretch)
│   └── Dockerfile
├── sample_kb/                   # Acme Cloud KB documents
│   └── malformed/               # bad files used by tests
├── docker/postgres/init/        # creates the test database
├── docs/
│   ├── PLAN.md                  # this file
│   ├── CODEZERO_NOTES.md        # development log of CodeZero usage
│   └── screenshots/
├── docker-compose.yml
├── .env.example
└── README.md                    # setup, architecture overview, API reference, decisions
```

---

## 4. Conventions

- **Errors:** every error response uses one envelope:
  `{"error": {"code": "TICKET_NOT_FOUND", "message": "Ticket not found", "details": null}}`.
  Domain code raises `AppError` subclasses (`NotFoundError`, `ForbiddenError`, `ConflictError`,
  `ValidationFailedError`); global handlers convert them, plus FastAPI `RequestValidationError`,
  `HTTPException` and unexpected exceptions (500, logged with request id, no stack trace leaked).
- **Layers:** routers stay thin (parse, call service, return schema). Business rules live in
  `services/`. Permission checks live in `core/permissions.py` / `core/deps.py`.
- **Transactions:** a state change and its `ticket_events` row are written in the same transaction.
- **Logging:** Python `logging`, one line per event, includes `request_id`. Log ingestion results,
  retrieval mode + latency + top score, fallbacks, permission denials, status changes.
- **IDs:** integer PKs for relational tables; UUIDs for `document_chunks` (shared with Qdrant point ids).
- **Timestamps:** `timestamptz`, UTC.
- **API prefix:** `/api`. OpenAPI docs at `/docs`.
- **Tests:** every work package ships with tests. Unit tests use a deterministic fake embedder and
  Qdrant `:memory:` mode; DB tests run against the `support_test` Postgres database.
- **Secrets:** only via environment variables. `.env` is never committed.

---

## 5. Data model

| Table | Columns |
|---|---|
| `users` | id, email (unique, lowercased), full_name, password_hash, role (`user`\|`agent`), created_at |
| `tickets` | id, title (5–200), description (10–5000), category (`account`\|`billing`\|`technical`\|`sync`\|`other`), priority (`low`\|`medium`\|`high`\|`urgent`), status, created_by → users, assigned_to → users (nullable), created_at, updated_at, `search_vector` tsvector (title + description, GIN index) |
| `ticket_comments` | id, ticket_id → tickets, author_id → users, body (1–5000), is_internal (bool), created_at |
| `ticket_events` | id, ticket_id, actor_id, event_type, data (jsonb), created_at — **append-only** |
| `documents` | id, title, filename, content_type, size_bytes, status (`processing`\|`ready`\|`failed`), error_message, vector_indexed (bool), chunk_count, uploaded_by → users, created_at |
| `document_chunks` | id (UUID), document_id → documents (ON DELETE CASCADE), chunk_index, page_number (nullable for TXT), text, `tsv` tsvector (GIN index) |
| `ticket_suggestions` | id, ticket_id, chunk_id → document_chunks (ON DELETE CASCADE), rank, score, retrieval_mode, created_at |

`event_type` values: `created`, `status_changed` (`{from, to}`), `assigned` (`{from_agent_id, to_agent_id}`),
`comment_added`, `internal_note_added`, `ticket_updated`.

Statuses: `open`, `in_progress`, `waiting_for_user`, `resolved`, `closed`.

---

## 6. Ticket workflow (state machine)

Defined once as a transition table in `services/workflow.py`.

| From | To | Allowed actor |
|---|---|---|
| open | in_progress | agent |
| in_progress | waiting_for_user | agent |
| waiting_for_user | in_progress | agent, **or automatic when the ticket owner posts a comment** |
| open / in_progress / waiting_for_user | resolved | agent |
| resolved | closed | owner or agent |
| resolved | open | owner (reopen) |
| closed | — | terminal, nothing allowed |

- Invalid transition → **409 Conflict**, `details.allowed` lists valid next statuses for that actor.
- Same-status "transition" → 409.
- Every change writes a `status_changed` event.
- API exposes allowed next statuses per ticket for the current user (`allowed_transitions` field
  on ticket detail) so the UI only renders valid buttons.

---

## 7. Permissions

| Action | user | agent |
|---|---|---|
| Create ticket | ✅ | ✅ |
| View ticket | own only | all |
| Edit title/description | own, while `open` | ❌ |
| Public comment | own tickets | ✅ |
| Internal note | ❌ (403) | ✅ |
| See internal notes / internal events | ❌ (never returned) | ✅ |
| Assign | ❌ | ✅ (assignee must be an agent) |
| Change status | owner transitions only (§6) | agent transitions (§6) |
| Upload / delete / reindex KB docs | ❌ | ✅ |
| Search KB | ✅ | ✅ |
| Agent dashboard | ❌ | ✅ |

- A user requesting another user's ticket gets **404, not 403** (prevents ID enumeration).
- Missing/invalid token → 401.
- `/auth/register` always creates role `user`; agents come from the seed script.

---

## 8. API

| Method | Path | Notes |
|---|---|---|
| POST | `/api/auth/register` | email, full_name, password (min 8) |
| POST | `/api/auth/login` | returns `{access_token, token_type, user}` |
| GET | `/api/auth/me` | |
| POST | `/api/tickets` | creates ticket + `created` event + suggestions snapshot |
| GET | `/api/tickets` | `q`, `status`, `priority`, `category`, `assigned=me\|unassigned`, `page`, `page_size` |
| GET | `/api/tickets/{id}` | includes `allowed_transitions` |
| PATCH | `/api/tickets/{id}` | owner, while open |
| POST | `/api/tickets/{id}/status` | `{status}` |
| POST | `/api/tickets/{id}/assign` | `{agent_id}` (agent only) |
| GET | `/api/tickets/{id}/comments` | internal filtered by role |
| POST | `/api/tickets/{id}/comments` | `{body, is_internal}` |
| GET | `/api/tickets/{id}/events` | internal events filtered by role |
| GET | `/api/tickets/{id}/suggestions` | stored snapshot |
| POST | `/api/tickets/{id}/suggestions/refresh` | re-run retrieval, replace snapshot |
| GET | `/api/dashboard/agent` | counts + my queue + unassigned (agent) |
| GET | `/api/users/agents` | for assignment dropdown (agent) |
| POST | `/api/kb/documents` | multipart `file`, optional `title` (agent) → 202 with `processing` doc |
| GET | `/api/kb/documents` | list |
| GET | `/api/kb/documents/{id}` | detail incl. status/error |
| DELETE | `/api/kb/documents/{id}` | removes from Postgres and Qdrant (agent) |
| POST | `/api/kb/documents/{id}/reindex` | re-embed into Qdrant (agent) |
| GET | `/api/kb/search` | `q`, `k` (default 3, max 10), `mode=auto\|semantic\|keyword` |
| GET | `/api/health` | `{db, qdrant, embedder}` status |

Search / suggestions response:

```json
{
  "mode": "semantic",
  "insufficient": false,
  "results": [
    {"chunk_id": "…", "document_id": 3, "document_title": "Billing & Refund Policy",
     "page": 2, "snippet": "…", "score": 0.78}
  ]
}
```

---

## 9. Retrieval pipeline

**Ingestion** (FastAPI `BackgroundTasks`; document starts as `processing`):

1. Validate: extension in {`.pdf`, `.txt`}; size ≤ `MAX_UPLOAD_MB`; PDFs must start with `%PDF`;
   TXT must decode as UTF-8 and must not be empty. Validation failures → 400/413/415 immediately.
2. Extract text: PDFs page by page (keep page numbers); TXT as one "page" (`page_number = null`).
   No extractable text → document `failed`, `error_message = "No extractable text (scanned or image-only PDF?)"`.
   Corrupt PDF → `failed` with a readable message.
3. Chunk: paragraph-aware, target ~800 characters, ~150 character overlap, never across pages.
4. Store chunks in Postgres (source of truth; `tsv` populated).
5. Embed + upsert into Qdrant with payload `{document_id, document_title, page, chunk_index}`.
   If Qdrant/embedder fails: document still `ready`, `vector_indexed = false` (keyword search still works; reindex later).
6. Document → `ready`, `chunk_count` set. Log outcome.

**Search** (`services/retrieval.py`):

1. `mode=auto`: try semantic (embed query → Qdrant top-k). On any exception from embedder/Qdrant,
   log a warning and fall back to keyword.
2. Keyword: `websearch_to_tsquery('english', q)` + `ts_rank_cd` over `document_chunks.tsv`.
3. `insufficient = true` when there are no results, or (semantic mode) the top score is below
   `RETRIEVAL_SCORE_THRESHOLD`. Results below threshold are dropped.
4. Response always states the `mode` actually used.

**On ticket creation:** query = `title + "\n" + description`, k = 3, snapshot into
`ticket_suggestions`. Retrieval failure must **never** fail ticket creation (log + empty snapshot).

**Evaluation (stretch, only if time remains after WP9):** `scripts/eval_retrieval.py` runs ~12
labelled queries (query → expected document) and prints hit@3 and MRR for semantic and keyword
modes. Until then the threshold is picked by hand against the sample KB and noted in the README.

---

## 10. Sample knowledge base — "Acme Cloud"

A fictional file storage & sync SaaS. Documents in `sample_kb/`:

| File | Format | Content |
|---|---|---|
| `getting-started-guide.pdf` | PDF, multi-page | Account setup, desktop/mobile apps, first sync |
| `account-login-troubleshooting.txt` | TXT | Password reset, 2FA, locked accounts, SSO |
| `billing-refund-policy.pdf` | PDF | Plans, invoices, payment failures, refunds, cancellation |
| `sync-troubleshooting.txt` | TXT | Sync conflicts, stuck uploads, storage quota, selective sync |
| `sharing-permissions-faq.pdf` | PDF | Share links, team folders, access levels, link expiry |
| `security-data-privacy.txt` | TXT | Encryption, retention, account deletion, data export |

`sample_kb/malformed/`: `empty.txt`, `corrupt.pdf`, `not-really.pdf` (text renamed to .pdf),
`image-only.pdf` (no text layer), `binary-garbage.txt` (non-UTF-8).

---

## 11. Frontend

Pages (responsive, Tailwind):

1. **Login / Register**
2. **Ticket list** — search box, status/priority/category filters, badges, simple prev/next paging.
   Users see their own tickets; agents see all.
3. **New ticket** — validated form; on submit, redirect to the ticket detail page, where the
   suggestions are shown. (No live suggestions while typing.)
4. **Ticket detail** — header (status, priority, category, assignee), conversation thread
   (internal notes highlighted, agents only), activity timeline, agent controls (assign dropdown,
   status buttons from `allowed_transitions`, reply box with "internal note" toggle), owner controls
   (close / reopen), **Suggested solutions** panel (title, page, snippet, score, mode badge,
   "not enough information" state, refresh button, **"Insert into reply"** for agents).
5. **Agent dashboard** — count cards (my open, unassigned, waiting for user, urgent), "My queue",
   "Unassigned" lists.
6. **Knowledge base** — upload (agents), document table (status, chunks, indexed, error, delete),
   search panel with passages, sources and mode badge.

JWT stored in `localStorage`; API client attaches it and redirects to login on 401.

---

## 12. Testing

**pytest** (`backend/tests/`):

- Tickets: create + validation errors; creation succeeds when retrieval fails.
- Workflow: every valid transition per role; every invalid transition → 409; closed is terminal;
  owner comment auto-moves `waiting_for_user → in_progress`; events written.
- Assignment: agent only; assignee must be an agent; event written.
- Permissions: user A → B's ticket = 404 (read, comment, status); user posting internal note = 403;
  internal notes/events never in user responses; no token = 401; user uploading KB doc = 403.
- Ingestion: each sample doc ingests with correct chunk/page data; each malformed file fails with
  the right error.
- Retrieval: relevant result for known queries; empty KB / nonsense query → `insufficient`;
  Qdrant failure → keyword fallback with `mode = keyword`; deleting a doc removes it from both stores.
- One `@pytest.mark.slow` test with the real fastembed model over `sample_kb/`.

**Playwright** (`frontend/e2e/`, stretch, only if time remains after WP9): one smoke spec against
the seeded stack — user logs in, creates a ticket and sees suggestions with sources; agent
assigns, replies and resolves; user closes. Permission cases stay covered by pytest.

---

## 13. Work packages (build order)

Each WP is one CodeZero planned session → reviewed plan → tasks → tests green → commit.

**Replan (2026-10-26, during WP6):** the original WP7–WP12 were merged into WP7–WP9 to finish
sooner. Simplified: the retrieval eval script and the Playwright smoke spec became stretch goals,
the new-ticket form no longer shows live suggestions (they appear on the ticket page after
creation), and ARCHITECTURE.md / API.md were folded into the README. Screenshots are taken by
hand. No requirement from the assignment brief was dropped.

| WP | Scope | Done when |
|---|---|---|
| WP0 | Repo skeleton, compose (postgres, qdrant), PLAN.md, CodeZero log | ✅ done |
| WP1 | Backend foundation: FastAPI app, config, db session, logging + request id, error envelope, `/api/health`, Alembic setup, pytest setup, Dockerfile, `backend` compose service | ✅ done |
| WP2 | Users + auth: model, migration, register/login/me, JWT deps, `require_agent` | ✅ done |
| WP3 | Tickets core: tickets/comments/events models + migration, create/list/detail/patch, comments, events, filters + search, permissions | ✅ done |
| WP4 | Workflow + assignment: state machine, status endpoint, assign endpoint, auto-transition on owner comment, `allowed_transitions` | ✅ done |
| WP5 | KB ingestion: documents/chunks models + migration, upload validation, extraction, chunking, background processing, list/detail/delete, sample KB docs + malformed fixtures | ✅ done |
| WP6 | Retrieval: embedder, Qdrant store, keyword search, retrieval service with fallback + threshold, `/api/kb/search`, suggestions on ticket create, refresh, reindex | retrieval tests green |
| WP7 | Backend wrap-up: seed script (2 agents, 2 users, sample KB ingested, ~8 tickets across all statuses with comments and internal notes; emails on a normal domain such as `@acme-demo.com`, because `.test`/`.local` are rejected), `GET /api/dashboard/agent`, `GET /api/users/agents` | seeded demo works; tests green |
| WP8 | Frontend: Vite + React (JS) + Tailwind + Router + TanStack Query, API client, auth context, layout/nav, login/register, ticket list (search + filters), new ticket form, ticket detail (thread, timeline, agent/owner controls, suggestions panel with "Insert into reply"), agent dashboard page, KB page (upload, document table, search panel), Dockerfile, `frontend` compose service | every page in §11 works in the browser against the seeded backend |
| WP9 | Delivery: README (setup, running locally, running tests, architecture overview, API reference table + link to `/docs`, key decisions, retrieval threshold notes), final summary in `CODEZERO_NOTES.md`. Screenshots are taken by hand, not by CodeZero; the README links to whatever is in `docs/screenshots/` | a fresh clone runs from the README alone |

### Definition of done for every work package

- Copy the approved plan from `~/.code0/plans/<plan-file>.md` into `docs/codezero/plans/`.
- Append an entry for the WP to `docs/CODEZERO_NOTES.md` using the template in that file.
- Run `docker compose run --rm backend pytest -q` and only commit if it passes. Frontend WPs
  must also pass `npm run build`.
- Commit messages: `WPn: <short summary>`. Never add `Co-Authored-By`, "Generated with",
  or any AI attribution lines to commits or PRs.
- Include the `.code0/` folder in the commit.
- Merge the WP branch into `main` and push both.
