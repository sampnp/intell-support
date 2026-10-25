# WP1 — Backend foundation

## Context

First backend work package from docs/PLAN.md §13. It gives every later WP (auth, tickets, workflow,
KB, retrieval) a running FastAPI app inside Docker, with config, a database session, logging with
request ids, the single error envelope (§4), a health endpoint, Alembic and a pytest harness that
runs against `support_test`. **Done when** (§13): `docker compose up` serves `/api/health`, and
pytest runs in the container.

There are no SQLAlchemy models, auth, tickets, KB or retrieval code in this WP. The repo has no
`backend/` yet; only `docker-compose.yml` (postgres, qdrant), `.env.example` and the test-DB init
script exist (commit e7c3b3a).

## Decisions

- **Embedder in /api/health:** the user chose a *placeholder now*. WP1 reports
  `"embedder": "not_configured"`. fastembed, the model download in the Dockerfile and the real
  embedder check are all added in WP6. Rejected: baking the model into the image in WP1, because it
  pulls WP6 scope forward and slows every build.

## Approach

All new files go under `backend/`, following the layout in PLAN.md §3. The order follows the tasks below.

### 1. Dependencies, config, DB session, Alembic skeleton
- `backend/requirements.txt` has exact `==` pins: fastapi, uvicorn[standard], pydantic v2,
  pydantic-settings, SQLAlchemy 2.0, psycopg[binary] 3, alembic, qdrant-client, pytest and httpx
  (httpx is needed by FastAPI's TestClient). qdrant-client is pinned to **1.12.x** to match the
  `qdrant/qdrant:v1.12.5` server, which avoids the client/server version-compatibility warning.
  It's one file because the tests run inside the same image.
- `app/config.py` has a `Settings(BaseSettings)` with `extra="ignore"`, because `.env` also
  carries VITE_/JWT keys that later WPs read. Fields: `postgres_user/password/host/port/db/test_db`,
  `qdrant_url`, `qdrant_collection`, `embedding_model`, `log_level`, `cors_origins` (comma list →
  list). Computed `database_url` / `test_database_url` use the `postgresql+psycopg://` scheme.
  `get_settings()` is wrapped in `lru_cache`. Only the keys WP1 uses are added; JWT, threshold and
  upload settings arrive with WP2/WP5/WP6.
- `app/db.py` has `engine = create_engine(url, pool_pre_ping=True, connect_args={"options": "-c timezone=utc"})`
  (this sets the UTC/timestamptz convention from §4). It also has
  `SessionLocal = sessionmaker(autoflush=False, expire_on_commit=False)`, and `get_db()` yields a
  session and closes it in `finally`. `Base(DeclarativeBase)` gets a `MetaData` with a constraint
  naming convention so Alembic autogenerate produces stable names.
- `app/models/__init__.py` re-exports `Base` only. It's the one place later WPs import their models
  so Alembic sees them.
- `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako` and `alembic/versions/` (empty, `.gitkeep`).
  `env.py` uses `target_metadata = app.models.Base.metadata`. Its URL is `sqlalchemy.url` when the
  caller set one (the test harness does), otherwise `settings.database_url`. No revision is created,
  because there are no tables yet.

### 2. Logging, request id, error envelope, app factory
- `app/core/logging.py`:
  - A `request_id` ContextVar. A `logging.Filter` injects it into every record (`-` outside a request).
  - `configure_logging(level)` sets a single-line format:
    `%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s`. Messages are
    written as `key=value` pairs.
  - The `RequestIdMiddleware` is pure ASGI, so no BaseHTTPMiddleware contextvar pitfalls:
    - It accepts an incoming `X-Request-ID` only if it matches `[A-Za-z0-9._-]{1,64}`, and
      otherwise generates `uuid4().hex`.
    - It stores the id in the contextvar and in `scope["state"]`, and echoes `X-Request-ID` on the
      response.
    - It logs one line per request: `method= path= status= duration_ms=`.
- `app/core/errors.py`:
  - `AppError(Exception)` has `status_code`, `code`, `message`, `details`. Subclasses:
    `NotFoundError` (404, `NOT_FOUND`), `ForbiddenError` (403, `FORBIDDEN`), `ConflictError`
    (409, `CONFLICT`), `ValidationFailedError` (422, `VALIDATION_FAILED`). Each takes optional
    `code`/`message`/`details` overrides, e.g. `NotFoundError("Ticket not found", code="TICKET_NOT_FOUND")`.
  - `register_exception_handlers(app)`. Every handler returns
    `{"error": {"code", "message", "details"}}`:
    - `AppError` → its own fields.
    - `RequestValidationError` → 422, `VALIDATION_ERROR`, details = the error list made
      JSON-safe (`loc`, `msg`, `type`).
    - Starlette `HTTPException` → status mapped to a code (`BAD_REQUEST`, `UNAUTHORIZED`,
      `FORBIDDEN`, `NOT_FOUND`, `METHOD_NOT_ALLOWED`, `CONFLICT`, `PAYLOAD_TOO_LARGE`,
      `UNSUPPORTED_MEDIA_TYPE`, else `HTTP_ERROR`). The exception's headers are kept, e.g.
      WWW-Authenticate for WP2. Registering on the Starlette class also covers unknown-route 404s.
    - `Exception` → 500, `INTERNAL_ERROR`, "Internal server error", `details: {"request_id": …}`.
      It logs with `logger.exception` (the traceback goes to the logs, never to the body) and sets
      `X-Request-ID` on the response.
- `app/main.py`:
  - `create_app(settings=None)` configures logging and builds `FastAPI(title="Intell-Support API",
    docs_url="/docs")`.
  - It adds CORS from `cors_origins` and `RequestIdMiddleware`, registers the handlers and includes
    `api.health.router` under the `/api` prefix.
  - The module-level `app = create_app()` is for uvicorn.

### 3. Health endpoint
- `app/services/vector_store.py` (the file §3 assigns to the Qdrant wrapper) contains **only**
  `get_qdrant_client()` → `QdrantClient(url=settings.qdrant_url, timeout=2)` for now. WP6 extends
  this file.
- `app/api/health.py`: `GET /api/health` depends on `get_db` and `get_qdrant_client`, so tests can
  override both.
  - db: runs `SELECT 1` → `"ok"`; any exception → `"error"` (logged as a warning).
  - qdrant: calls `client.get_collections()` → `"ok"`; any exception → `"error"`.
  - embedder: `"not_configured"` (decision above).
  - Response: `{"status": "ok"|"degraded", "db", "qdrant", "embedder"}`. Status is `degraded`
    when db or qdrant is `error`.
  - It always returns HTTP 200: it's a status report, not an error, so it doesn't conflict with
    the envelope convention. A Pydantic response schema goes in `app/schemas/health.py`.

### 4. Docker
- `backend/Dockerfile`:
  - Base image `python:3.12-slim` with `PYTHONDONTWRITEBYTECODE=1` and `PYTHONUNBUFFERED=1`.
  - `pip install --no-cache-dir -r requirements.txt` runs before `COPY . .` to keep the layer cache.
  - Runs as a non-root `app` user with workdir `/app` and exposes 8000.
  - Default `CMD`: `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000`.
  - `backend/.dockerignore` excludes caches, `.venv` and `__pycache__`.
- `docker-compose.yml` gets a `backend` service:
  - It builds `./backend` and uses `env_file: .env`.
  - Explicit `environment` sets `POSTGRES_HOST: postgres`, `POSTGRES_PORT: "5432"`,
    `QDRANT_URL: http://qdrant:6333` and `WATCHFILES_FORCE_POLLING: "true"`. These must override
    `.env`, whose `POSTGRES_PORT` is the *host-published* port. Polling is needed because Windows
    and OneDrive bind mounts don't deliver inotify events.
  - It publishes `${BACKEND_PORT:-8000}:8000` and mounts `./backend:/app` for dev.
  - The command adds `--reload` to the Dockerfile CMD.
  - `depends_on`: postgres `service_healthy`, qdrant `service_started`.
  - The header comment is updated. `BACKEND_PORT=8000` is added to `.env.example`.

### 5. pytest setup and WP1 tests
- `backend/pytest.ini` sets `testpaths = tests` and registers the `slow` marker (§12).
- `tests/conftest.py`:
  - Session fixture: a test engine on `settings.test_database_url`. It **refuses to run unless the
    DB name ends in `_test`**, so tests can't touch the dev DB. It runs
    `alembic.command.upgrade(cfg, "head")` against that URL, so every later WP's migrations are
    exercised by the suite.
  - Per-test `db_session`: a connection, an outer transaction and a `Session(bind=conn,
    join_transaction_mode="create_savepoint")`, rolled back afterwards.
  - The `app` fixture is `create_app()` with `get_db` overridden to that session and
    `get_qdrant_client` overridden to `QdrantClient(location=":memory:")`. The `client` fixture is
    a `TestClient(app, raise_server_exceptions=False)`.
- Tests:
  - `tests/test_health.py`:
    - All ok against `support_test` + in-memory Qdrant → 200, `status=ok`, `embedder=not_configured`.
    - A Qdrant stub that raises → `qdrant=error`, `status=degraded`.
    - A DB session stub that raises → `db=error`.
  - `tests/test_errors.py` (test-only routes added to a `create_app()` instance):
    - Each `AppError` subclass → correct status and envelope; a custom code override is honoured.
    - Body validation failure → 422 `VALIDATION_ERROR` with details.
    - Unknown route → 404 `NOT_FOUND` envelope; `HTTPException(401, headers=…)` keeps its header.
    - A route raising `RuntimeError("secret")` → 500 `INTERNAL_ERROR`, and the body contains
      neither "secret" nor "Traceback".
  - `tests/test_request_id.py`:
    - A generated id is returned in `X-Request-ID`.
    - A valid incoming id is echoed; an invalid one (too long or with bad chars) is replaced.
    - The 500 body's `details.request_id` equals the header.
    - A log record emitted during a request carries the id (`caplog`).

## Risks

- **Bind mount over `/app`** hides the image's copied source in dev. That's intended for
  `--reload`; the image still runs standalone without the mount.
- **`alembic upgrade head` on start** is a no-op in WP1 (no revisions), but it fails fast if
  Postgres is unreachable. `depends_on: service_healthy` covers normal startup.
- **Out of scope:** models and migrations, auth/JWT settings, the fastembed/model download, a
  compose healthcheck for backend, README/API docs (WP12), and CODEZERO_NOTES (the user writes that).

## Verification

Run from the repo root on the host (PowerShell):

1. `docker compose config --quiet` should exit 0 (compose file valid).
2. `docker compose up -d --build` should build the backend image; postgres, qdrant and backend
   should all be running.
3. `curl.exe -s http://localhost:8000/api/health` should return
   `{"status":"ok","db":"ok","qdrant":"ok","embedder":"not_configured"}`.
4. `docker compose run --rm backend pytest -q` should pass all tests against `support_test`.
5. `docker compose logs backend --tail 20` should show single-line request logs containing
   `request_id=`.
