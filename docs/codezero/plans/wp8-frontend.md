# WP8 — Frontend

## Context

WP8 in the replanned docs/PLAN.md §13 is the whole frontend:
- Vite, React (JavaScript), Tailwind, React Router and TanStack Query
- the API client and auth context, layout and nav
- login and register
- the ticket list with search and filters, and the new-ticket form
- ticket detail: thread, timeline, agent and owner controls, and the suggestions panel with
  "Insert into reply"
- the agent dashboard
- the KB page: upload, document table and search
- the Dockerfile and the `frontend` compose service

**Done when:** every page in §11 works in the browser against the seeded backend.

The backend is complete (WP1–WP7), and the dev stack is seeded with demo accounts
(`priya@acme-demo.com` / `demo-password` and others). `CORS_ORIGINS` already allows
`http://localhost:5173`, and `.env` has `VITE_API_BASE_URL=http://localhost:8000/api`.

## Decisions

- **The Vite dev server with hot reload runs in compose on port 5173.** `npm run build` still
  runs as a check, as the definition of done requires. Rejected: an nginx production build, and
  both.
- **Tests are Vitest and Testing Library for the risky parts:**
  - the API client: token, error envelope, a 401 logging you out
  - route guards
  - status buttons coming only from `allowed_transitions`
  - the suggestions panel: the insufficient state, and "Insert into reply" for agents only

  Rejected: build only.

Defaults stated to you before planning, with no objection raised:
- **A backend `healthcheck` in compose** polls `/api/health`, and `frontend` waits for
  `service_healthy`. This removes the `--reload` startup gap for everything that depends on the
  backend.
- **Health checks use your `curl.exe --retry …` form** from PLAN.md.
- **Node runs only in Docker:** `npm install`, test and build. The lockfile is generated inside
  the container.
- **The JWT is stored in `localStorage`** (§11), and any 401 logs you out and sends you to login.
- **I can't open a browser here.** The final click-through is yours. I verify that the dev server
  serves the app, the build and tests pass, and the backend answers the CORS preflight from
  `localhost:5173`.

## Approach

### 0. Remove the Code-Zero trailer from `main`, then branch

*Added after the first Run.* code0 auto-committed your uncommitted PLAN.md edit, the
retrying-curl rule, as `ea9a925` "Work in progress on code0/…wp7-backend-wrapup". It went onto
local `main` with a `Co-authored-by: Code-Zero` trailer. Nothing is pushed: `origin/main` is
`f74cabc`. You chose to fix it inside this plan, so a single Run does both the fix and WP8.

1. Check with the read-only git tools that `origin/main..main` is exactly `ea9a925`, touching
   only `docs/PLAN.md`. If it's anything else, stop and report.
2. Run `git checkout main`.
3. Run `git reset --soft HEAD~1`. `main` goes back to `f74cabc`, with the PLAN.md edit still
   staged.
4. Run `git commit -m "Docs: health checks use a retrying curl"`. This is the same content,
   without the trailer.
5. Check that the new commit's parent is `f74cabc`, that `git diff ea9a925 main` is empty, and
   that `origin/main..main` contains no `Co-authored-by`.
6. Run `git checkout -b wp8-frontend` from that clean `main`. If code0 moves branches or adds
   commits during the run, I re-check before the merge and before the push, and stop if
   anything foreign appears.

### 0b. Repair the branches before committing (added after the second Run)

**State after the second Run.**
- Tasks 0–6 are done and verified, all in the working tree:
  - `main` was cleaned to `79d1806`, and `wp8-frontend` was branched from it
  - frontend, compose, tests and docs are written
  - 36 Vitest tests pass, the build passes, and backend `pytest` gives 325 passed
  - the mutation check caught all three breaks (2/1/1 failures, all reverted)
  - the stack is healthy, the dev server serves the app, and the CORS preflight is allowed
- Then, outside my commands, local `main` was moved back to `da7dd8d` (WP4) and `HEAD` was
  switched. The next Run put `HEAD` on code0's branch at `ea9a925`, its trailer commit, whose
  tree is identical to `79d1806`.
- Nothing is lost:
  - `wp8-frontend` is still at the clean `79d1806`
  - `origin/main` is at `f74cabc`
  - all WP8 changes are in the working tree

**The repair** moves refs only, never files. Order matters: a branch that's currently checked out
can't be force-moved.
1. Check with the read-only git tools that `wp8-frontend` is at `79d1806`, that `79d1806`'s parent
   is `origin/main`, and that `git diff 79d1806` (working tree) is only WP8 files. If any of
   that is wrong, stop and report.
2. Run `git symbolic-ref HEAD refs/heads/wp8-frontend`. This puts `HEAD` on the clean branch, and
   files stay as they are.
3. Run `git reset -q`. The index now matches `79d1806`, so only WP8 changes show.
4. Run `git branch -f main 79d1806`. `main` is back on the clean history.
5. Re-check `git status`, the branches, and `origin/main..main` (just the docs commit, with no
   trailer). Then re-run `npm test`, `npm run build` and `pytest`, and continue with step 7 of
   the definition of done: commit, `git checkout main`, merge, push, and the checkbox commit.
   Before pushing, I check again that no commit with a trailer is an ancestor of `main`.

### 1. Scaffold, Docker, compose
- **`frontend/package.json`:** exact pins.
  - App:
    - `react` / `react-dom` 18.3.1
    - `react-router-dom` 6.28.0
    - `@tanstack/react-query` 5.62.0
  - Build:
    - `vite` 5.4.11
    - `@vitejs/plugin-react` 4.3.4
    - `tailwindcss` 3.4.16
    - `postcss` 8.4.49
    - `autoprefixer` 10.4.20
  - Tests:
    - `vitest` 2.1.8
    - `jsdom` 25.0.1
    - `@testing-library/react` 16.1.0
    - `@testing-library/dom` 10.4.0
    - `@testing-library/jest-dom` 6.6.3
    - `@testing-library/user-event` 14.5.2
  - Scripts: `dev`, `build`, `preview`, `test` (`vitest run`).
- **`vite.config.js`:**
  - the React plugin
  - the server on `0.0.0.0:5173`, `strictPort`, with `watch.usePolling`, because file events
    don't cross Windows bind mounts
  - Vitest with `jsdom`, `globals` and a setup file that loads jest-dom
- **`tailwind.config.js`, `postcss.config.js`, `index.html`, `src/index.css`.**
- **`frontend/Dockerfile`:** `node:20-alpine`, `WORKDIR /app`, `COPY package*.json`,
  `npm install`, `COPY . .`, `EXPOSE 5173`, `CMD npm run dev`.
  - `frontend/.dockerignore` excludes `node_modules` and `dist`.
- **`docker-compose.yml`:**
  - **backend** gets a `healthcheck`: Python `urllib` against `/api/health`, interval 5 s,
    start_period 20 s, retries 30.
  - **New `frontend` service:**
    - builds `./frontend`, with `env_file: .env`
    - ports `${FRONTEND_PORT:-5173}:5173`
    - volumes `./frontend:/app` plus an anonymous `/app/node_modules`
    - `depends_on: backend: service_healthy`
  - The header comment is updated.
- **Lockfile:** `docker compose run --rm --no-deps frontend npm install` writes
  `package-lock.json` into the bind mount, and it gets committed.

### 2. API client, auth, layout, routing, login/register
- **`src/api/client.js`:**
  - `apiRequest(path, {method, query, body, form})`:
    - the base URL is `import.meta.env.VITE_API_BASE_URL`, falling back to
      `http://localhost:8000/api`
    - it attaches `Authorization: Bearer` from `localStorage`
    - it handles JSON or `FormData` bodies, skips empty query params, and returns `null` on 204
  - Non-2xx responses throw `ApiError {status, code, message, details}` from the §4 envelope.
  - A 401 clears the token and calls a registered `onUnauthorized` handler.
- **`src/api/endpoints.js`:** one function per backend endpoint, grouped as `auth`, `tickets`,
  `dashboard`, `users` and `kb`.
- **`src/context/AuthContext.jsx`:**
  - It holds `user`, `loading`, `login`, `register` and `logout`.
  - On load with a stored token it calls `/auth/me`.
  - Its `onUnauthorized` handler logs out and navigates to `/login`.
- **`src/components/`:**
  - `Layout`: the nav shows Tickets and New ticket; Dashboard and Knowledge base for agents;
    Knowledge base (search) for users; the user's name and role; and Log out.
  - `RequireAuth({role})`: no user goes to `/login` (keeping `from`); the wrong role goes to `/`.
  - `StatusBadge`, `PriorityBadge`, `ModeBadge`, `ErrorBanner`, `Spinner`.
- **`src/lib/format.js`:**
  - status, priority and category labels
  - relative and absolute dates
  - `describeEvent(event)`, which handles `created`, `status_changed` (including automatic),
    `assigned` (including unassigned), comments, internal notes and edits
- **Pages:**
  - `LoginPage` and `RegisterPage`: validated forms that show the API error message.
  - `/` redirects agents to `/dashboard` and users to `/tickets`.
  - `NotFoundPage`.
- **`main.jsx` / `App.jsx`:** `QueryClientProvider`, `BrowserRouter`, `AuthProvider` and the
  routes.

### 3. Ticket list + new ticket
- **`TicketListPage`:**
  - a search box, debounced 300 ms
  - status, priority and category selects, plus "Assigned: me / unassigned" for agents
  - a table with title, badges, created by, assignee and updated time
  - prev/next paging driven by `total` / `page_size` (§11)
  - the filters live in URL search params
- **`NewTicketPage`:**
  - title (5–200), description (10–5000), category and priority (default medium)
  - client-side checks matching the API, with the API's 422 details shown per field
  - on success it redirects to `/tickets/{id}`, where the suggestions are shown (§11: no live
    suggestions while typing)

### 4. Ticket detail
- **`TicketDetailPage`:** the header shows title, status, priority, category, created by and
  assignee. A ticket the API returns 404 for (missing or not yours) shows "Ticket not found".
- **`CommentThread`:** internal notes are highlighted. Only agents ever receive them.
- **`Timeline`:** events through `describeEvent`.
- **`ReplyBox`:** the body, plus an "Internal note" toggle for agents only. It's disabled with a
  message when the ticket is closed. Its text is controlled by the page, so "Insert into reply"
  can append to it.
- **`StatusButtons`:** one button per `allowed_transitions` entry, with friendly labels such as
  "Start work", "Wait for user", "Resolve", "Close ticket" and "Reopen". This covers both the
  agent controls and the owner's close and reopen.
- **`AssignControl`** (agents): a dropdown of `/users/agents` plus "Unassigned". It's hidden on
  closed tickets, and shows the API error when there is one.
- **`SuggestionsPanel`:**
  - It shows the mode badge and when the snapshot was last updated.
  - Each result shows the document title, page and score, plus the passage text.
  - There's a "Not enough information in the knowledge base" state, and a Refresh button.
  - **"Insert into reply"** is for agents only. It appends the passage plus
    `(Source: <title>, p. <page>)` to the reply box.
- Every mutation invalidates the ticket, comments, events and suggestions queries.

### 5. Agent dashboard + knowledge base
- **`DashboardPage`** (agents): four count cards (my open, unassigned, waiting for user, urgent),
  then "My queue" and "Unassigned" lists linking to the tickets.
- **`KnowledgeBasePage`:**
  - **Search panel** (everyone): a query, a mode selector (auto, semantic or keyword) and `k`.
    The results show passages, source title and page, and score, with a mode badge and the
    insufficient state. A 503 for semantic search shows the API message.
  - **Upload form** (agents): file plus optional title. Upload errors (400/413/415) show their
    message.
  - **Document table** (agents): status, chunks, indexed, error, and Reindex / Delete buttons.
    Delete asks for confirmation. The table refetches every 2 s while any document is
    `processing`.

### 6. Tests (Vitest + Testing Library)
- **`src/api/client.test.js`**, with `fetch` stubbed:
  - the bearer header is attached
  - JSON and FormData bodies are sent correctly
  - empty query params are dropped
  - the error envelope becomes an `ApiError`
  - a 401 clears the token and calls `onUnauthorized`
  - a 204 returns `null`
- **`src/components/RequireAuth.test.jsx`:**
  - a logged-out visitor is sent to `/login`
  - a user on an agent route is sent to `/`
  - an agent sees the page
- **`StatusButtons.test.jsx`:**
  - it renders exactly the allowed transitions, with labels
  - it renders nothing for `[]`
  - a click reports the status
- **`SuggestionsPanel.test.jsx`:**
  - the insufficient state
  - result fields and mode badge
  - Insert shown only when allowed, and passing the passage with its source
  - Refresh is called
- **`src/lib/format.test.js`:** `describeEvent` for each event type, including automatic and
  unassign.

### 7. Definition of done (CLAUDE.md, PLAN.md §13)
1. Copy this plan to `docs/codezero/plans/wp8-frontend.md`.
2. Mutation check: break three rules one at a time, confirm the tests fail, then revert.
   - Status buttons show every status.
   - "Insert into reply" is shown to users.
   - The client doesn't clear the token on 401.
3. Append a WP8 entry to `docs/CODEZERO_NOTES.md`.
4. All must pass before committing:
   - `npm test` and `npm run build` in the frontend container
   - `docker compose run --rm backend pytest -q`, since the compose file changed
5. `docker compose up -d backend frontend`, then:
   - health, using the retrying curl
   - the dev server serving `index.html`
   - the CORS preflight from `localhost:5173` returning `access-control-allow-origin`
   - `docker compose ps` showing backend `healthy`
6. Check `git log origin/main..HEAD` and `git status` for foreign changes.
7. Commit `WP8: …` including `.code0/` and `package-lock.json`, with no AI attribution. Merge
   into `main` with `--no-ff` and push both branches.
8. After the last task is marked complete, commit `Mark WP8 CodeZero tasks complete` and push
   `main`.

## Risks

- **Pinned npm versions** must resolve from the registry. If one doesn't, I'll stop and report
  rather than pick another version.
- **The anonymous `node_modules` volume** keeps old packages after dependencies change.
  Rebuilding needs `docker compose up -d --build -V frontend`. That goes in the README in WP9.
- **Out of scope:**
  - a UI for editing a ticket's title and description (the API exists, but §11 doesn't list it)
  - Playwright (a stretch goal)
  - the README (WP9)

## Verification

0. Before any WP8 work, `origin/main..main` should contain only
   "Docs: health checks use a retrying curl", with no trailer and the same content as `ea9a925`.
   After the 0b repair, `HEAD` should be on `wp8-frontend` at `79d1806`, `main` should be at
   `79d1806`, and `git status` should show only WP8 files.
1. `docker compose run --rm --no-deps frontend npm test` should pass all Vitest suites.
2. `docker compose run --rm --no-deps frontend npm run build` should build `dist/` with no
   errors.
3. `docker compose run --rm backend pytest -q` should still pass all 325 tests.
4. `docker compose up -d backend frontend`, then:
   - the retrying `curl.exe` on `/api/health` should report `ok`
   - `curl.exe … http://localhost:5173/` should return the Vite `index.html`
   - the preflight `curl.exe -i -X OPTIONS -H "Origin: http://localhost:5173" …/api/auth/login`
     should show `access-control-allow-origin: http://localhost:5173`
5. **By hand in the browser at http://localhost:5173:**
   - As `dana@acme-demo.com`: see 4 tickets, create one, and see its suggestions with sources.
     Close or reopen a resolved ticket.
   - As `priya@acme-demo.com`:
     - the dashboard counts show 4/2/1/1
     - assign a ticket, reply, add an internal note, and use "Insert into reply"
     - move a ticket through its statuses
     - upload a document and search the KB
