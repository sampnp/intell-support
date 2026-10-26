# WP6 — Retrieval

## Context

Sixth work package from docs/PLAN.md §13. It covers:
- the embedder and the Qdrant store
- keyword search
- a retrieval service that tries semantic search first, falls back to keyword, and applies a
  threshold
- `/api/kb/search`
- suggestions on ticket creation, plus refresh
- reindex

**Done when** (§13): the retrieval tests are green.

It completes §9. WP5 left marked hooks for embed and upsert in `process_document`, for removing
the Qdrant points in document delete, and for suggestions in `create_ticket`. Health still
reports `embedder: not_configured`, and `get_qdrant_client` still opens a client per request.
That was the WP1 follow-up.

## Decisions

- **Snapshot metadata lives on the ticket.** Two nullable columns, `tickets.suggestions_mode`
  (`semantic` | `keyword`) and `tickets.suggestions_updated_at`. An empty snapshot can then still
  say which mode ran and when. This is a small addition to §5. Rejected: rows only, which would
  make an empty snapshot report `mode: null`.
- **Explicit `mode=semantic` with Qdrant or the embedder down gives 503
  `SEMANTIC_UNAVAILABLE`.** Only `mode=auto` falls back to keyword. Rejected: silently falling
  back.

Defaults stated to you before planning, with no objection raised:
- **The model ships in the image.** fastembed's `BAAI/bge-small-en-v1.5` is downloaded at build
  time into `/opt/fastembed`, outside the `/app` bind mount. It loads lazily on first use.
- **One shared Qdrant client**, and the collection is created if missing.
- **If indexing fails during ingestion,** the document is still `ready` with
  `vector_indexed=false` (§9).
- **Delete removes the Qdrant points on a best-effort basis.** If that fails, it's logged and the
  Postgres delete still happens. Search always joins results back to Postgres, so orphan points
  never show.
- **Reindex** is agent-only and synchronous, works on `ready` documents only, and gives 503 if
  Qdrant or the embedder is down.
- **The snippet is the whole stored passage** (≤ ~950 chars), so "Insert into reply" pastes
  something complete. Only `ready` documents are searched. Keyword scores are normalized to 0–1.
- **Search is open to any signed-in user.** Suggestions follow the ticket's visibility rules,
  and so does refresh.
- **Tests** use a deterministic hashing fake embedder and in-memory Qdrant. One
  `@pytest.mark.slow` test uses the real model and runs in the normal `pytest -q`; `pytest.ini`
  already documents `-m "not slow"` to skip it.

## Approach

Work happens on branch `wp6-retrieval`, created before task 1.

### 1. Embedder, Qdrant store, health
- `requirements.txt`: add `fastembed==0.4.2`.
- `config.py`: add
  - `retrieval_score_threshold: float = 0.5` (already in `.env.example`)
  - `embedding_dim: int = 384`
  - `embedding_cache_dir: str = "/opt/fastembed"`
- `Dockerfile`:
  - Set `ENV FASTEMBED_CACHE_PATH=/opt/fastembed`.
  - After `pip install`, a `RUN python -c "...TextEmbedding('BAAI/bge-small-en-v1.5')"` step
    downloads the model, with `ARG EMBEDDING_MODEL` defaulting to the bge model.
  - `chown` the cache directory to the `app` user.
- `services/embeddings.py`:
  - An `Embedder` Protocol with `dim`, `embed_passages(list[str]) -> list[list[float]]`,
    `embed_query(str) -> list[float]` and `check()`.
  - `FastEmbedEmbedder` loads `TextEmbedding` lazily behind a lock, and uses fastembed's
    `passage_embed` / `query_embed`. On load it checks that the vector size equals
    `embedding_dim`.
  - `get_embedder()` is an `lru_cache`d dependency.
- `services/vector_store.py`:
  - `get_qdrant_client()` becomes an `lru_cache`d **shared** client (timeout 5 s) instead of a
    per-request generator.
  - A `VectorStore(client, collection, dim)` class provides:
    - `ensure_collection()`: creates it with cosine distance if `collection_exists` is false
    - `upsert_chunks(document, chunks, vectors)`: point id = chunk UUID, payload
      `{document_id, document_title, page, chunk_index}` (§9)
    - `search(vector, limit) -> list[(UUID, score)]`
    - `delete_document(document_id)`: deletes by payload filter
    - `count_for_document(document_id)`
  - `get_vector_store()` is a dependency.
- `core/errors.py`: add `ServiceUnavailableError` (503).
- `api/health.py`: `embedder` becomes `ok` / `error` via `embedder.check()`, and an error makes
  the response `degraded`.

### 2. Keyword search + retrieval service
- `services/keyword_search.py`: `keyword_search(db, q, k) -> list[SearchHit]` runs
  `websearch_to_tsquery('english', q)` against `document_chunks.tsv`, joined to documents with
  `status='ready'`.
  - Score is `ts_rank_cd(tsv, query, 32)`, which is normalized to 0–1, ordered score desc, then
    `document_id` and `chunk_index`.
  - A query made only of stopwords returns `[]`.
- `services/retrieval.py`:
  - `SearchHit {chunk_id, document_id, document_title, page, snippet, score}`.
  - `SearchResult {mode, insufficient, results}`.
  - `semantic_search(...)`:
    - It runs `embed_query`, then `store.search(limit=k*2)`.
    - It loads those chunks from Postgres, from ready documents only, keeping Qdrant's order.
    - It drops scores below the threshold and keeps the top `k`.
  - `search(db, embedder, store, q, k, mode, threshold)`:
    - **auto**: try semantic. On *any* exception, log
      `retrieval_fallback reason=...` at warning and use keyword.
    - **semantic**: any exception raises 503 `SEMANTIC_UNAVAILABLE`.
    - **keyword**: keyword search only.
    - `insufficient = not results`. Semantic results are already threshold-filtered, so this
      covers "top score below threshold".
    - It logs one line: `retrieval mode= requested= k= results= top_score= latency_ms=`.

### 3. Indexing on ingest, delete, reindex
- `services/ingestion.py`:
  - `index_chunks(embedder, store, document, chunks)` runs `ensure_collection`,
    `embed_passages`, then `upsert_chunks`.
  - `process_document(..., embedder=None, store=None)`:
    - It flushes the chunks, then tries `index_chunks`.
    - Success sets `vector_indexed=True`.
    - Any exception logs `ingestion_vector_index_failed` and sets `vector_indexed=False`. The
      document is still `ready`.
  - `process_in_background` and `ingest_bytes` pass the embedder and store through.
- `api/kb.py`:
  - **Upload** depends on `get_embedder` and `get_vector_store`, and hands them to the
    background task.
  - **Delete** calls `store.delete_document` on a best-effort basis; a failure is logged.
  - **`POST /kb/documents/{id}/reindex`** (agent):
    - A document that isn't `ready` gives 409 `DOCUMENT_NOT_READY`.
    - Otherwise it deletes the old points, then indexes the chunks loaded from Postgres, sets
      `vector_indexed=True` and returns `DocumentOut`.
    - On failure it sets `vector_indexed=False` and gives 503 `VECTOR_INDEX_UNAVAILABLE`.

### 4. Search endpoint + ticket suggestions
- `schemas/retrieval.py`:
  - `SearchHitOut` and `SearchResponse {mode, insufficient, results}`, exactly the §8 shape.
  - `SuggestionsResponse`, which is the same plus `updated_at`.
- `GET /api/kb/search` (any signed-in user):
  - `q` is stripped and must be 1–500 chars; blank gives 422.
  - `k` defaults to 3, with `1 ≤ k ≤ 10`.
  - `mode` is `auto|semantic|keyword` and defaults to `auto`.
- `models/ticket.py` + migration `0004_ticket_suggestions.py`:
  - `TicketSuggestion` columns:
    - `id`
    - `ticket_id` FK, ON DELETE CASCADE, indexed
    - `chunk_id` UUID FK `document_chunks`, **ON DELETE CASCADE**
    - `rank`, unique per ticket
    - `score` float
    - `retrieval_mode`, with a CHECK
    - `created_at`
  - `Ticket` gains `suggestions_mode` (nullable, CHECK) and `suggestions_updated_at`.
- `services/suggestions.py`:
  - `snapshot_suggestions(db, ticket, embedder, store, threshold)`:
    - The query is `title + "\n" + description`, with `k=3` and `mode=auto`.
    - It replaces the ticket's rows and sets `suggestions_mode` and `suggestions_updated_at`, all
      in one commit.
    - **It never raises.** On any failure it rolls back, logs `suggestions_failed ticket_id=`,
      and leaves an empty snapshot with mode null.
  - `get_suggestions(db, ticket)` reads the rows by rank, joining chunk and document.
- `services/tickets.create_ticket(..., suggest=None)`: after the ticket and its `created` event
  are committed, it calls the snapshot function if one is given. The router passes one; the
  `make_ticket` test fixture doesn't, so tests outside retrieval are unaffected.
- `api/tickets.py`:
  - `POST /tickets` wires in the snapshot.
  - `GET /tickets/{id}/suggestions` and `POST /tickets/{id}/suggestions/refresh` both go through
    `get_visible_ticket` (someone else's ticket gives 404).

### 5. Tests
- `tests/fakes.py`:
  - `HashingEmbedder` (dim 384): lowercase word tokens, a small stopword list, md5 bucket counts,
    L2-normalized. It's deterministic, and cosine similarity reflects word overlap.
  - `FailingEmbedder`, and a `BrokenStore` whose methods raise.
- `conftest.py`:
  - It overrides `get_embedder` with `HashingEmbedder`, and `get_vector_store` with
    `VectorStore(in-memory client, "kb_chunks", 384)`.
  - An autouse fixture sets `retrieval_score_threshold` to 0.1, which suits the fake embedder.
  - An `indexed_kb` fixture ingests the 6 sample docs through `ingest_bytes` with the fakes.
- `tests/test_vector_store.py`:
  - `ensure_collection` is idempotent.
  - Upsert and search return the chunk UUIDs and payload.
  - `delete_document` removes only that document's points.
  - The fake embedder is deterministic and normalized.
- `tests/test_retrieval.py`:
  - **Known queries** for semantic and keyword, each expecting its document in the top 3:
    - a refund for a duplicate charge → billing
    - 2FA codes rejected → login
    - conflicted copy → sync
    - share link expiry password → sharing
    - export my data → security
    - install the desktop app → getting started
  - An **empty KB** gives `insufficient` in all modes.
  - A **nonsense query** gives `insufficient`.
  - **Threshold:** at 0.99, semantic gives `insufficient` with no results, and results are never
    below the threshold.
  - **Fallback:** with `BrokenStore` or `FailingEmbedder`, `auto` returns `mode: keyword` with
    results and a logged fallback, while explicit `semantic` gives 503 `SEMANTIC_UNAVAILABLE`.
  - **Validation:** `k` of 0 or 11 gives 422, blank `q` gives 422, and there are at most `k`
    results.
  - **Access:** a user can search, and no token gives 401.
  - **Shape:** every hit has the §8 fields.
- `tests/test_indexing.py`:
  - **Ingest:** a successful ingest sets `vector_indexed`, and the point count equals the chunk
    count with the right payload.
  - **Ingest with a broken store:** the document is still ready with `vector_indexed=false`,
    keyword still finds it, and a reindex with a working store sets it indexed so semantic finds
    it.
  - **Reindex:**
    - a user gets 403
    - a failed document gives 409
    - a broken store gives 503 with `vector_indexed` left false
    - it's idempotent: the point count is unchanged after a second run
  - **Delete:** delete removes the document from **both stores**, and search no longer returns
    it.
  - **Health:** `embedder: ok` with the fake, and `error` plus `degraded` when `check()` raises.
- `tests/test_suggestions.py`:
  - **Ticket creation:** creating a ticket against `indexed_kb` stores ≤ 3 ranked rows, and
    `GET` returns `mode: semantic`, `insufficient: false`, sources and the relevant document.
  - **Retrieval failure** (search monkeypatched to raise) gives **201** anyway, and `GET` shows
    an empty snapshot with `mode: null` and `insufficient: true`; the failure is logged.
  - An **empty KB** gives `mode: semantic`, `insufficient: true`.
  - **Refresh** after uploading a relevant doc replaces the rows and moves `updated_at` forward.
  - **Delete:** deleting a document cascades its suggestion rows away.
- `tests/test_ticket_permissions.py`: add both suggestion endpoints to the "someone else's ticket
  gives 404" matrix and the no-token matrix.
- `tests/test_real_embedder.py` (`@pytest.mark.slow`):
  - It uses `FastEmbedEmbedder`, in-memory Qdrant and the sample KB at the real 0.5 threshold.
  - Four known queries have their document in the top 3 with top score ≥ threshold, and the
    vectors are 384-dim and normalized.

### 6. Definition of done (CLAUDE.md)
1. Copy this plan to `docs/codezero/plans/wp6-retrieval.md`.
2. Mutation check: break three rules one at a time, confirm the tests fail, then revert.
   - `auto` re-raises instead of falling back.
   - The threshold is not applied.
   - Ticket creation isn't protected from retrieval failure.
3. Append a WP6 entry to `docs/CODEZERO_NOTES.md`.
4. `docker compose run --rm backend pytest -q` must pass before committing.
5. Check `git log origin/main..HEAD` and `git status` for anything I didn't make.
6. Commit `WP6: …` including `.code0/`, with no AI attribution. Merge into `main` with
   `--no-ff` and push both branches.
7. After the last task is marked complete, commit `Mark WP6 CodeZero tasks complete` and push
   `main`.

## Risks

- **Build size and network.** The image grows by onnxruntime and the model (about 100 MB), and
  the build needs network access to Hugging Face. If the pinned `fastembed` doesn't resolve
  against the existing pins, I'll stop and report rather than pick another version.
- **Real-model scores.** The 0.5 threshold is a placeholder until WP7's eval script tunes it.
  The slow test only asserts hit@3 and top score ≥ threshold, never exact scores.
- **First-request latency.** The first semantic call after a restart loads the model (about
  1–2 s). Health triggers that load too.
- **Out of scope:** the eval script, seeding, the dashboard and `/users/agents` (all WP7), and
  every frontend piece.

## Verification

1. `docker compose build backend` installs fastembed and downloads the model into the image.
2. `docker compose run --rm backend pytest -q` should pass everything: the earlier 248 plus the
   new retrieval tests, including the slow real-model test.
3. `docker compose up -d backend` runs migration 0004. Once it's up,
   `curl.exe -s http://localhost:8000/api/health` should report
   `{"status":"ok","db":"ok","qdrant":"ok","embedder":"ok"}`.
4. By hand in `/docs`:
   - As an agent, upload `sample_kb/billing-refund-policy.pdf`; it should show
     `vector_indexed: true`.
   - `GET /api/kb/search?q=refund for a duplicate charge` should return `mode: semantic` with the
     billing passage.
   - Create a ticket about a double charge, and `GET /api/tickets/{id}/suggestions` should list
     it.
