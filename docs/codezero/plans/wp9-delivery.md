# WP9 — Delivery: README, retrieval evaluation, final CodeZero summary

## Context

This is the last work package in the replanned docs/PLAN.md §13. It covers:
- the README: setup, running locally, running tests, an architecture overview, an API reference
  table with a link to `/docs`, key decisions, and retrieval threshold notes
- the final summary in `docs/CODEZERO_NOTES.md`

Screenshots are taken by hand, and the README links to `docs/screenshots/`.

**Done when:** a fresh clone runs from the README alone.

The current README is a WP0 stub ("Work in progress… infrastructure only").

**Repository state left over from WP8.**
- After WP8's last task was marked complete, local refs moved without any command from me:
  - `HEAD` is on `wp8-frontend` (`125d575`)
  - local `main` is stuck at `79d1806`, 2 behind `origin/main` (`fb3bc63`, the pushed WP8 merge)
  - the WP8 checkbox file is modified
- GitHub is correct and complete.

## Decisions

- **The retrieval threshold is backed by real numbers.** This adds the stretch eval script
  `scripts/eval_retrieval.py` now, and its output goes in the README. Rejected: justifying 0.5 in
  prose only.
- **I draft the "Summary (written at the end)" in CODEZERO_NOTES** from the WP log, clearly marked
  as a draft for you to edit before submitting. Rejected: leaving the four headings empty.

Defaults stated to you before planning, with no objection raised:
- Step 0 repairs the refs inside this run.
- `.env.example` gains `FRONTEND_PORT` and `SEED_PASSWORD`.
- The README commands are verified against the running stack. A true fresh clone in a separate
  folder is your check, since ports would clash.

## Approach

### 0. Repair refs and commit the WP8 checkbox (refs only, no file changes)

This runs before anything else. It works whether or not code0 auto-commits at Run time.
1. Check the state with the read-only git tools:
   - `origin/main` is at `fb3bc63`
   - `fb3bc63`'s tree equals `wp8-frontend` (`125d575`)
   - `HEAD` is **not** on `main`
   - the working tree differs only in `.code0/tasks/*.md`

   If any of that is wrong, stop and report.
2. Run `git branch -f main origin/main`. Local `main` becomes `fb3bc63`.
3. Run `git symbolic-ref HEAD refs/heads/main`, then `git reset -q`. `HEAD` is now on `main`, with
   files unchanged.
4. Run `git add .code0/tasks/6adf61669cb64fb3236a5fbf.md`, then
   `git commit -m "Mark WP8 CodeZero tasks complete"`, then `git push origin main`.
5. Run `git checkout -b wp9-delivery`.

### 1. Retrieval evaluation script
- `backend/scripts/eval_retrieval.py`, run with `python -m scripts.eval_retrieval` against the
  seeded dev stack, using the real model and Qdrant:
  - **`LABELLED`:** 12 natural-language questions, two per sample document, each mapped to the
    expected `filename`. They're written as a customer would phrase them, not copied from the
    documents.
  - **`OFF_TOPIC`:** 4 questions the KB can't answer, such as "best banana bread recipe" or
    "how do I change my car's oil".
  - **`evaluate(db, embedder, store, modes)`:** for each mode, it runs `retrieval.search` with
    `k=10` and `threshold=0.0`, so it sees the raw ranking. It returns, per mode:
    - hit@3
    - MRR@10
    - per-query rank and top score
  - **Semantic score spread:**
    - the lowest top-1 score among relevant queries that hit
    - the highest top-1 score among off-topic queries
    - for the configured threshold, how many relevant queries survive it, and how many off-topic
      queries are wrongly let through
  - **`main()`:**
    - It checks that the sample documents are ingested and `ready`, and otherwise exits 2 with
      "run the seed first".
    - It prints a per-query table and a summary block, ready to paste into the README.
  - **Metric helpers:** `hit_at_k(ranks, k)` and `mean_reciprocal_rank(ranks)` are pure functions
    so they can be tested.
- `backend/tests/test_eval_retrieval.py`:
  - The metric helpers on hand-made ranks: a hit, a miss, rank 1, rank 3, not found.
  - `evaluate()` with the hashing fake and `indexed_kb` returns a row for every query in both
    modes, with values between 0 and 1. This is a smoke test, not a quality claim.
- Run it on the seeded dev stack and record the real numbers.

### 2. README rewrite
`README.md` gets these sections:
1. **What it is:** one paragraph, plus the feature list (users, agents, workflow, KB, semantic
   suggestions with keyword fallback, no LLM).
2. **Screenshots:** a link to `docs/screenshots/`, which you add by hand.
3. **Quick start**, with Docker Desktop as the only prerequisite:
   1. `cp .env.example .env`, then set `JWT_SECRET` (with the one-liner from `.env.example`).
   2. `docker compose up -d --build`. The backend waits for Postgres, the frontend waits for a
      healthy backend, and the first build downloads the embedding model.
   3. `docker compose run --rm backend python -m scripts.seed`.
   4. Open http://localhost:5173. The API docs are at http://localhost:8000/docs.
   5. A demo accounts table: 2 agents and 2 users, password `demo-password`.
4. **Running tests:**
   - backend: `docker compose run --rm backend pytest -q`, or `-m "not slow"` to skip the
     real-model test
   - frontend: `npm test` and `npm run build` through `docker compose run --rm --no-deps frontend`
5. **Everyday commands:**
   - reset the demo with `--reset`
   - rebuild after dependency changes with `docker compose up -d --build -V frontend`
   - regenerate the sample KB with `python scripts/build_sample_kb.py`
   - run the retrieval evaluation
   - follow the logs
6. **Architecture overview:**
   - a component diagram (Mermaid): browser, React, FastAPI, Postgres / Qdrant / fastembed
   - backend layers (api, services, core, models)
   - the data model in one table
   - the ticket state machine table
   - the ingestion pipeline and the retrieval flow (semantic first, then keyword with all words
     first and any word second, threshold, insufficient)
   - how suggestions are snapshotted
7. **API reference:** every endpoint, with method, path, who may call it, and notes. It links to
   the live `/docs`, and describes the error envelope and the main codes (401, 403, 404, 409, 413,
   415, 422, 503).
8. **Key decisions:** each with a one-line "why", for example:
   - no LLM, so suggestions are extractive
   - Postgres is the source of truth and Qdrant only an index
   - 404, not 403, for other users' tickets
   - append-only events enforced by a trigger
   - the suggestion snapshot stores its mode on the ticket
   - explicit semantic search gives 503, while auto falls back
   - keyword search tries all words, then any word
   - the agent-only document list
   - seed skip / `--reset`
   - the backend healthcheck
   - the JWT in `localStorage`
9. **Retrieval threshold notes:** the eval script's real output, why `0.5` was chosen or changed,
   and how to change `RETRIEVAL_SCORE_THRESHOLD`.

   **If the numbers show 0.5 is clearly wrong, I don't change it myself.** I report it, and you
   decide.
10. **Known limitations:**
    - the dev servers aren't production builds
    - `npm audit` reports 12 advisories in the pinned dev toolchain
    - the JWT is in `localStorage`
    - there's no ticket-edit UI
    - Playwright isn't done (stretch)
    - English-only full-text search
11. **Project layout** tree, plus links to PLAN.md, CODEZERO_NOTES.md and `docs/codezero/plans/`.
- `.env.example`: add `FRONTEND_PORT=5173` and `SEED_PASSWORD=demo-password`, both commented.

### 3. CodeZero log
- Append a WP9 entry: prompt, decisions, the ref repair, the eval numbers, and verification.
- Fill in "Summary (written at the end)" as a **draft marked "Draft written by CodeZero from this
  log — review and edit before submitting"**. It's built only from facts in the log:
  - **helped:** questions it raised that weren't in the spec, the mutation checks catching gaps
    (WP7), and stopping before pushing the trailer
  - **wrong / needed correction:** the WP6 test pollution of the dev Qdrant, keyword AND-search
    being useless for long text (found by a test), and the WP7 mutation gap
  - **verified:** tests in Docker per WP, mutation checks, health and CORS checks, and manual
    browser checks
  - **differently:** commit my own edits before Run, keep the tree clean between plans, and keep
    one WP per plan

### 4. Definition of done (CLAUDE.md)
1. Copy this plan to `docs/codezero/plans/wp9-delivery.md`.
2. Mutation check (one rule): break `mean_reciprocal_rank` (use rank instead of 1/rank), confirm
   the test fails, then revert.
3. All must pass:
   - `docker compose run --rm backend pytest -q` (325 plus the new eval tests)
   - `npm test` and `npm run build`
4. Walk the README quick start against the running stack:
   - `docker compose up -d --build` and `docker compose ps` (backend healthy)
   - health and the frontend checked with the retrying curl
   - the seed reporting "already seeded"
   - the eval script's output matching the README
5. Check `git log origin/main..HEAD` and `git status` for foreign changes.
6. Commit `WP9: …` including `.code0/`, with no AI attribution. Merge into `main` with `--no-ff`
   and push both branches.
7. After the last task is marked complete, re-check the refs. If code0 moved them again, run the
   same refs-only repair (`git branch -f main origin/main` when `HEAD` isn't `main`, then
   `git symbolic-ref HEAD refs/heads/main` and `git reset -q`). Then commit the WP9 checkbox file
   and push.

## Risks

- **Real-model scores could show 0.5 is too strict or too loose.** I report the numbers and leave
  the value to you.
- **The README can't prove a fresh clone works** from inside this checkout. That's your final
  check (§13 "done when").
- **Out of scope:**
  - Playwright
  - screenshots
  - fixing the `npm audit` advisories (a version-upgrade decision)
  - deleting the stale local `code0/*` branches, which code0 may still use

## Verification

0. After step 0, `HEAD` should be on `main` at `origin/main`, and the WP8 checkbox commit should
   be pushed. `wp9-delivery` should be branched from it.
1. `docker compose run --rm backend pytest -q` should pass everything, including
   `test_eval_retrieval.py`.
2. `docker compose run --rm backend python -m scripts.eval_retrieval` should print hit@3, MRR and
   the score spread for both modes, and the README should quote exactly that.
3. `npm test` should pass 36 and `npm run build` should succeed.
4. `docker compose up -d --build` should leave every container up and the backend healthy.
   Health should report `ok` and the frontend should serve `index.html`. The seed should report
   "already seeded".
5. **By hand:** follow the README on a fresh clone, open http://localhost:5173, log in with a demo
   account, and add screenshots to `docs/screenshots/`.
