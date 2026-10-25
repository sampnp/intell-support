# Implement WP1 (backend foundation) exactly as described in docs/PLAN.md §2, §3, §4 and §13. Include: FastAPI app factory, pydantic-settings config, sync SQLAlchemy engine/session + get_db, structured logging with request-id middleware, the AppError hierarchy and error-envelope handlers, GET /api/health (db, qdrant, embedder status), Alembic setup, pytest setup against the support_test database, a Python 3.12 backend Dockerfile, and a `backend` service in docker-compose.yml. Do not implement any models or features beyond WP1.

Plan: `6ade75cbda84b55fbd168edc`
Repositories: sampnp/intell-support

## Tasks

- [x] Dependencies, config, DB session, Alembic skeleton
- [x] Logging, request id, error envelope, app factory
- [x] GET /api/health
- [x] Backend Dockerfile and compose service
- [x] pytest setup and WP1 tests

---

Written by code0 when the plan was approved. The plan itself lives outside this
repository — see `~/.code0/plans/` — because a plan can span repositories and is
not a source file. This note is the thread back to it.
