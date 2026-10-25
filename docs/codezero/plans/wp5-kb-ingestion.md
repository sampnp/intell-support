# WP5 — KB ingestion

## Context

Fifth work package from docs/PLAN.md §13. It covers:
- the documents and chunks models plus their migration
- upload validation, text extraction and chunking
- background processing
- list, detail and delete for documents
- the "Acme Cloud" sample KB and the malformed fixtures (§10)

**Done when** (§13): the ingestion tests are green.

It follows ingestion steps 1–4 and 6 from §9. **Step 5 (embed and upsert into Qdrant) is WP6.**
So in WP5 every document ends `ready` or `failed` with `vector_indexed = false`, and delete
removes the document from Postgres only. WP6 adds the Qdrant side.

## Decisions

- **Sample PDFs and binary bad files come from a generator script.** I write the Acme Cloud
  content, and `scripts/build_sample_kb.py` builds the files reproducibly with **fpdf2**, a
  tools-only dependency. The generated files are committed, so tests and the WP7 seed just read
  them. Rejected: you supplying the PDFs.
- **The document list and detail are agents only**, like upload and delete. Users still get
  passages and titles through search and suggestions (WP6). Rejected: any signed-in user.
- **The same filename can be uploaded again** and becomes a separate document. Rejected: 409.

Defaults stated to you before planning, with no objection raised:
- **Validation failures are immediate, and nothing is stored:**
  - a wrong extension gets 415
  - a file over `MAX_UPLOAD_MB` gets 413
  - an empty file, a TXT that isn't UTF-8, or a "PDF" without `%PDF` gets 400
- **Readable failures:** a corrupt or image-only PDF is accepted with 202 and then marked
  `failed` with a readable message.
- **No file storage:** the uploaded file isn't kept, because Postgres chunks are the source of
  truth.
- **Default title:** the filename without its extension.
- **Mounting:** `sample_kb/` is mounted into the backend container.

## Approach

Work happens on branch `wp5-kb-ingestion`, created before task 1.

### 1. Config, dependencies, models, migration 0003
- `requirements.txt`: add `pypdf==5.1.0`, `python-multipart==0.0.20` (FastAPI needs it for
  `UploadFile` / `Form`) and, under a "tools" comment, `fpdf2==2.8.1`.
- `config.py`: add `max_upload_mb: int = 10` and `sample_kb_dir: str = "/sample_kb"`.
- `docker-compose.yml`, backend service: add the volume `./sample_kb:/sample_kb` and the
  environment variable `SAMPLE_KB_DIR: /sample_kb`.
- `core/errors.py`: add `BadRequestError` (400), `PayloadTooLargeError` (413) and
  `UnsupportedMediaTypeError` (415).
- `models/document.py`:
  - **`DocumentStatus`** StrEnum: `processing`, `ready`, `failed`.
  - **`Document`** columns:
    - `id`
    - `title` String(200)
    - `filename` String(255)
    - `content_type` String(100)
    - `size_bytes`
    - `status`, with a CHECK and default `processing`
    - `error_message` Text, nullable
    - `vector_indexed` bool, default false
    - `chunk_count` int, default 0
    - `uploaded_by` FK users
    - `created_at`

    Relationship: `uploader`.
  - **`DocumentChunk`** columns:
    - `id` UUID, with a Python `uuid4` default. It will be shared with the Qdrant point id (§4).
    - `document_id` FK **ON DELETE CASCADE**, indexed
    - `chunk_index`, unique per document
    - `page_number`, nullable
    - `text` Text
    - `tsv` TSVECTOR, `Computed("to_tsvector('english', text)", persisted=True)`, with a GIN index

    The tsvector is generated, like `tickets.search_vector`.
  - The models are registered in `models/__init__.py`.
- `alembic/versions/0003_create_documents.py` (down_revision `0002`) creates both tables, their
  constraints and indexes, and has a downgrade.
- `.gitattributes`: add `sample_kb/malformed/* binary`. Otherwise `text=auto eol=lf` could
  rewrite the bytes in `binary-garbage.txt` or `corrupt.pdf`.

### 2. Chunking + ingestion service
- `services/chunking.py` (pure functions, no I/O):
  - `chunk_pages(pages: list[tuple[int | None, str]], target=800, overlap=150) -> list[ChunkData]`
    returns `(chunk_index, page_number, text)`.
  - For each page:
    - Normalize: split into paragraphs on blank lines, collapse whitespace inside each
      paragraph, and drop NUL characters (Postgres can't store them).
    - Break pieces down until each is ≤ `target`: paragraphs into sentences, and sentences into
      word windows.
    - Pack the pieces greedily into chunks of new text ≤ `target`.
    - Start each following chunk with the last ≤ `overlap` characters of the previous one, cut
      at a word boundary.
  - Chunks **never span pages**. Empty pages produce none. `chunk_index` runs across the whole
    document.
- `services/ingestion.py`:
  - `validate_upload(filename, data, max_bytes) -> kind`:
    - The extension must be `.pdf` or `.txt` (case-insensitive), otherwise 415
      `UNSUPPORTED_FILE_TYPE`.
    - The size limit gives 413 `FILE_TOO_LARGE`.
    - An empty file gives 400 `EMPTY_FILE`.
    - A PDF without the `%PDF` magic, or a TXT that fails to decode as UTF-8, gives 400
      `INVALID_FILE`. The message names which check failed.
  - `extract_pages(kind, data)` returns the pages:
    - **TXT** comes back as `[(None, text)]`.
    - **PDF** goes through `pypdf.PdfReader`, giving `[(page_no, text)]` for each page.
    - These raise `ExtractionError` with readable messages:
      - `PdfReadError` and similar: "Could not read the PDF (the file may be corrupt)"
      - encrypted files: "Encrypted PDFs are not supported"
      - no text on any page: exactly `"No extractable text (scanned or image-only PDF?)"`
        (§9)
  - `create_document(db, user, filename, title, content_type, size)` writes the `processing`
    row and commits.
  - `process_document(db, document, data)` extracts, chunks and stores the chunks, then sets
    `ready`, `chunk_count` and `vector_indexed=False` and commits.
    - `ExtractionError` gives `failed` with its message.
    - Any other exception gives `failed` with "Unexpected error while processing the file",
      logged with its traceback.
    - It never raises.
    - It logs one line: `ingestion document_id= status= pages= chunks= duration_ms=` and, on
      failure, `error=`.
    - A `# WP6: embed + upsert` hook is marked.
  - `ingest_bytes(db, user, filename, data, title=None)` validates, creates and processes
    synchronously. Tests and the WP7 seed use it.
  - `get_session_factory()` is a dependency that returns a context manager yielding a fresh
    `SessionLocal()`.
    - The background task runs
      `with factory() as db: process_document(db, db.get(Document, id), data)`, so it never
      reuses the request's session.
    - The conftest overrides it to yield the test session.

### 3. KB API
- `schemas/kb.py`: `DocumentOut` has these fields:
  - `id`, `title`, `filename`, `content_type`, `size_bytes`
  - `status`, `error_message`, `vector_indexed`, `chunk_count`
  - `uploaded_by` as a `UserSummary` read from `uploader`
  - `created_at`
- `api/kb.py`, `APIRouter(prefix="/kb")`, included in `main.py`. Every route depends on
  `require_agent`.
  - `POST /documents`: multipart `file` plus an optional `title` Form field (stripped, ≤ 200).
    It reads at most `max_bytes + 1` bytes, validates, creates the row, queues
    `BackgroundTasks`, and returns **202** `DocumentOut` (`processing`).
  - `GET /documents`: newest first, `list[DocumentOut]`.
  - `GET /documents/{id}`: 404 `DOCUMENT_NOT_FOUND` if missing.
  - `DELETE /documents/{id}`: 204. The chunks go with it by cascade. A `# WP6` hook is marked for
    removing the Qdrant points.

### 4. Sample KB
- Hand-written TXT documents in `sample_kb/`, each several sections and realistic:
  - `account-login-troubleshooting.txt`: password reset, 2FA, locked accounts, SSO
  - `sync-troubleshooting.txt`: conflicts, stuck uploads, storage quota, selective sync
  - `security-data-privacy.txt`: encryption, retention, account deletion, data export
- `sample_kb/malformed/empty.txt` (0 bytes) and `not-really.pdf` (plain text) are written by
  hand.
- `backend/scripts/build_sample_kb.py` (fpdf2, with a fixed creation date for reproducible
  output) writes into `SAMPLE_KB_DIR`:
  - `getting-started-guide.pdf`, 3 pages: account setup, desktop and mobile apps, first sync
  - `billing-refund-policy.pdf`, 2 pages: plans and invoices, payment failures, refunds,
    cancellation
  - `sharing-permissions-faq.pdf`, 2 pages: share links, team folders, access levels, link expiry
  - `malformed/corrupt.pdf`: a `%PDF-1.4` header followed by junk, with no xref or trailer
  - `malformed/image-only.pdf`: a page with only drawn shapes and no text layer
  - `malformed/binary-garbage.txt`: fixed bytes that are invalid UTF-8
- It runs once with `docker compose run --rm backend python scripts/build_sample_kb.py`, and the
  output is committed.

### 5. Tests
- `conftest.py`:
  - It overrides `get_session_factory` to yield `db_session`.
  - A `sample_kb` fixture gives the `Path(settings.sample_kb_dir)`, and fails clearly if the
    folder isn't mounted.
  - An `upload(client, headers, path_or_bytes, filename, title=None)` helper.
- `tests/test_chunking.py`:
  - Short text gives 1 chunk.
  - Paragraphs are packed, with new text ≤ 800 and total ≤ 950.
  - Each chunk after the first starts with the previous chunk's tail.
  - A single huge paragraph and a run-on word sequence are both split.
  - Whitespace and NULs are normalized.
  - Empty pages are skipped.
  - Pages are never mixed in a chunk, and `chunk_index` is contiguous.
- `tests/test_ingestion.py`:
  - **Each of the 6 sample docs** through the API:
    - 202 with `processing` in the response, then `ready` on detail
    - `chunk_count` equals the number of rows and is > 0, and `vector_indexed` is false
    - PDFs have chunks on pages 1..N (the guide covers all 3 pages), and TXT chunks have
      `page_number` null
    - a word known to be in the doc matches its chunks through `tsv @@ websearch_to_tsquery`
  - **Malformed files:**
    - `empty.txt`, `binary-garbage.txt` and `not-really.pdf` get 400 with the right code, and
      no document row is created
    - `corrupt.pdf` gets 202, then `failed` with the corrupt message
    - `image-only.pdf` gets 202, then `failed` with the exact §9 message
    - `.docx` gets 415, and a file over the limit (limit lowered with monkeypatch) gets 413
  - **Titles:** the default title is the filename stem, and a custom title is stripped.
  - **Duplicates:** the same file twice gives two documents.
  - **List, detail and delete:**
    - the list is newest first, and an unknown id gives 404
    - delete gives 204 and its chunks are gone, and deleting again gives 404
  - An unexpected error inside processing (chunker monkeypatched to raise) gives `failed` with
    the generic message.
  - The ingestion log line is emitted.
  - **Permissions:** a user gets 403 `AGENT_REQUIRED` on all 4 endpoints, and no token gets 401.

### 6. Definition of done (CLAUDE.md)
1. Copy this plan to `docs/codezero/plans/wp5-kb-ingestion.md`.
2. Mutation check: break three rules one at a time, confirm the tests fail, then revert.
   - Let chunks span pages.
   - Skip the `%PDF` magic check.
   - Mark an image-only PDF `ready` with 0 chunks.
3. Append a WP5 entry to `docs/CODEZERO_NOTES.md`.
4. `docker compose run --rm backend pytest -q` must pass before committing.
5. Check `git log origin/main..HEAD` for foreign commits.
6. Commit `WP5: …` including `.code0/`, with no AI attribution. Merge into `main` with
   `--no-ff` and push both branches.
7. After the last task is marked complete, commit `Mark WP5 CodeZero tasks complete` and push
   `main`.

## Risks

- **fpdf2's built-in fonts are Latin-1 only.** The PDF text is kept to plain ASCII punctuation.
- **pypdf text extraction varies slightly between versions.** That's why the tests assert pages,
  counts and known words, never exact chunk text from PDFs.
- **Out of scope** (all WP6): embeddings, Qdrant upsert and delete, reindex, search, suggestions
  and the `ticket_suggestions` table. Seeding is WP7.

## Verification

1. `docker compose build backend` installs pypdf, python-multipart and fpdf2.
2. `docker compose run --rm backend python scripts/build_sample_kb.py` writes the 3 PDFs and 3
   malformed binaries into `sample_kb/`.
3. `docker compose run --rm backend pytest -q` should pass everything: the earlier 206 plus the
   new chunking and ingestion tests.
4. `docker compose up -d backend` runs migration 0003. Once it's up,
   `curl.exe -s http://localhost:8000/api/health` should report `ok`.
5. By hand in `/docs`, as an agent: upload `sample_kb/billing-refund-policy.pdf`, and
   `GET /api/kb/documents/{id}` should show `ready` with chunks. Uploading
   `malformed/image-only.pdf` should show `failed` with the §9 message.
