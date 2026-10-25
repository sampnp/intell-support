# WP2 — Users + auth

## Context

Second work package from docs/PLAN.md §13: users model + migration, register / login / me,
JWT dependencies and `require_agent`. Every later WP (tickets, workflow, KB, dashboard) depends on
`get_current_user` / `require_agent`. **Done when** (§13): auth tests green.

It builds on WP1 (`badac0d`): the settings in `app/config.py`, `Base` with naming convention in
`app/db.py`, the `AppError` envelope in `app/core/errors.py`, the conftest that migrates
`support_test` to head and rolls back each test, and Alembic with no revisions yet.

## Decisions

- **Register returns token + user**, the same body as login: `{access_token, token_type, user}`,
  status 201. The user is logged in straight away, and the frontend (WP8) has one code path for both.
  Rejected: returning just the user, which forces a second request.
- **Login takes a JSON body `{email, password}`**, consistent with every other endpoint and the JS
  client. Swagger `/docs` uses an HTTP Bearer scheme: you paste the token into Authorize.
  Rejected: the OAuth2 password form.

Technical choices, stated to you before planning, with no objection raised:
- `bcrypt` is used directly. passlib is unmaintained and breaks with bcrypt ≥ 4.1.
- Password must be 8 chars minimum and **72 bytes** maximum (UTF-8). bcrypt cannot hash more than
  72 bytes, so a longer password gets a 422, not a 500.
- `JWT_SECRET` is **required**, with no default, so the app fails to start rather than signing
  with a known key. `.env` already has it.
- The token carries only `sub` (user id), `iat` and `exp`. The role is read from the DB on every
  request, so a role change takes effect immediately.

## Approach

All work happens on branch `wp2-users-auth`, created from `main` before task 1.

### 1. Dependencies, settings, security helpers
- `backend/requirements.txt`: add exact pins `PyJWT==2.10.1`, `bcrypt==4.2.1` and
  `email-validator==2.2.0` (needed by Pydantic `EmailStr`).
- `app/config.py`: add `jwt_secret: str` (required), `jwt_expire_minutes: int = 480` and
  `jwt_algorithm: str = "HS256"`. `.env.example` already has `JWT_SECRET` / `JWT_EXPIRE_MINUTES`,
  so it stays unchanged.
- `app/core/errors.py`: add `UnauthorizedError(AppError)` (401, `UNAUTHORIZED`). `AppError` gets
  an optional class attribute `headers: dict | None = None`, which `handle_app_error` passes to
  `error_response`. `UnauthorizedError.headers = {"WWW-Authenticate": "Bearer"}`. Domain code
  keeps raising `AppError`s as §4 requires, and the 401s still carry the RFC 6750 header.
- `app/core/security.py`:
  - `hash_password(pw)` / `verify_password(pw, hash)` wrap `bcrypt.hashpw` /
    `bcrypt.checkpw`. The cost comes from a module constant `BCRYPT_ROUNDS = 12`, which the tests
    lower.
  - `create_access_token(user_id) -> str` and `decode_access_token(token) -> int`. The decoder
    returns the user id and raises `UnauthorizedError(code="INVALID_TOKEN")` on any `jwt.PyJWTError`
    (bad signature, malformed, expired) or a missing or non-integer `sub`. It requires
    `exp`/`sub` via `options={"require": [...]}`.

### 2. User model + migration
- `app/models/user.py`: `class Role(StrEnum): user, agent`. `User` has these columns:
  - `id` int PK
  - `email` String(254), unique, with CHECK `email = lower(email)`
  - `full_name` String(100)
  - `password_hash` String(60)
  - `role` String(20), default `user`, with CHECK `role IN ('user','agent')`. A plain string plus
    CHECK, not a native PG enum, so later migrations stay simple.
  - `created_at` timestamptz with `server_default now()`
  - Imported in `app/models/__init__.py` so Alembic sees it.
- `alembic/versions/0001_create_users.py`: hand-written first revision (`revision = "0001"`) that
  creates `users` with the constraint names produced by the WP1 naming convention. The conftest
  already runs `upgrade head`, so the suite exercises it.

### 3. Schemas, service, router, deps
- `app/schemas/auth.py`:
  - `RegisterRequest`:
    - `email: EmailStr`, lowercased.
    - `full_name`, stripped, 1–100 chars.
    - `password`, min 8, plus a validator that rejects more than 72 UTF-8 bytes.
    - There is no `role` field; extra keys are ignored, so `role: "agent"` in the body has no effect.
  - `LoginRequest`: `email`, lowercased, and `password`. No length rules, so a wrong password is
    always a 401, never a 422 that leaks the policy.
  - `UserOut`: id, email, full_name, role, created_at, with `from_attributes=True`. It never
    includes `password_hash`.
  - `TokenResponse`: `access_token`, `token_type="bearer"`, `user: UserOut`.
- `app/services/auth.py` holds the business rules:
  - `register_user(db, data) -> User`:
    - If the email exists, it raises `ConflictError("Email already registered", code="EMAIL_ALREADY_REGISTERED")`.
    - It also catches `IntegrityError` on commit (a concurrent duplicate) and raises the same 409.
    - The role is always `user` (§7).
  - `authenticate(db, email, password) -> User`:
    - It raises `UnauthorizedError("Invalid email or password", code="INVALID_CREDENTIALS")` for
      both an unknown email and a wrong password.
    - For an unknown email it checks against a dummy hash, so response time doesn't reveal which
      emails exist.
  - Logs: `auth_register user_id=`, `auth_login outcome=ok user_id=` and
    `auth_login outcome=failed`. Emails and passwords are never logged.
- `app/core/deps.py`:
  - `bearer = HTTPBearer(auto_error=False)`. With `auto_error=True`, FastAPI 0.115 returns 403
    for a missing token, but §7 requires 401.
  - `get_current_user(credentials, db) -> User`:
    - Missing credentials → `UnauthorizedError("Not authenticated", code="NOT_AUTHENTICATED")`.
    - A non-Bearer scheme or an invalid token → `INVALID_TOKEN`.
    - A token whose user no longer exists → `INVALID_TOKEN`.
  - `require_agent(user = Depends(get_current_user)) -> User`: when the role isn't `agent`, it logs
    `permission_denied user_id= reason=agent_required path=` and raises
    `ForbiddenError("Agent role required", code="AGENT_REQUIRED")`.
- `app/api/auth.py`, `APIRouter(prefix="/auth", tags=["auth"])`:
  - `POST /register` → 201 `TokenResponse`.
  - `POST /login` → 200 `TokenResponse`.
  - `GET /me` → `UserOut`.
  - The router is included in `app/main.py` under `/api`.

### 4. Tests
- `tests/conftest.py`:
  - An autouse fixture monkeypatches `security.BCRYPT_ROUNDS` to 4 to keep the suite fast.
  - Reusable fixtures for WP3+: `make_user(role=..., email=...)` inserts a user via
    `db_session`, and `auth_headers(user)` returns `{"Authorization": "Bearer …"}`.
  - Plus `user` and `agent` fixtures.
  - Test emails use `@example.com`, because email-validator rejects special-use domains such as
    `.test`/`.local`.
- `tests/test_auth.py`:
  - Register → 201 with a working token, role `user`, email lowercased, no `password_hash` in the
    body, and a DB hash that isn't the plaintext. `role: "agent"` in the body is ignored.
  - A duplicate email in a different case → 409 `EMAIL_ALREADY_REGISTERED`.
  - 422 `VALIDATION_ERROR` for an invalid email, a 7-char password, a 73-byte password and a blank
    `full_name`.
  - Login works with a mixed-case email, and its token works on `/me`. A wrong password and an
    unknown email both → 401 `INVALID_CREDENTIALS` with an identical message.
  - `/me`:
    - No header → 401 `NOT_AUTHENTICATED` with `WWW-Authenticate: Bearer`.
    - The `Basic` scheme, a garbage token, a wrong-secret token, an expired token, and a token for
      a deleted user → 401 `INVALID_TOKEN`.
- `tests/test_deps.py`: a test-only route behind `require_agent`, as in the `test_errors.py`
  pattern. User → 403 `AGENT_REQUIRED`, agent → 200, no token → 401.
- `tests/test_security.py`:
  - The hash/verify round-trip, and a wrong password fails.
  - A token round-trips to the user id.
  - Tampered and expired tokens raise `UnauthorizedError`.
- `tests/test_errors.py`: add a case for `UnauthorizedError` (envelope plus `WWW-Authenticate`).

### 5. Definition of done (CLAUDE.md)
1. Copy this plan to `docs/codezero/plans/wp2-users-auth.md`.
2. Append a WP2 entry to `docs/CODEZERO_NOTES.md` using its template: the prompt, the two
   decisions, what was generated, issues, verification and the mutation check.
3. Mutation check, as in WP1: temporarily break three rules, confirm the tests fail, then revert.
   - Make `require_agent` let users through.
   - Accept an expired token.
   - Let register honour `role`.
4. `docker compose run --rm backend pytest -q` must pass. Only then commit.
5. Commit on `wp2-users-auth` with the message `WP2: users and auth (user model + migration,
   register/login/me, JWT deps, require_agent)`, including `.code0/`. **No Co-Authored-By or any
   AI attribution lines** (CLAUDE.md overrides the default trailer).
6. Merge into `main` and push both branches.

## Risks

- `JWT_SECRET` is now required: running Alembic or the app outside compose without it fails at
  import. That's intended; compose's `env_file: .env` supplies it.
- WP7 seed accounts must use a normal domain (e.g. `@acme.example.com`), because
  `.test`/`.local` emails are rejected by `EmailStr`.
- Out of scope: refresh tokens, logout and token revocation, rate limiting, password reset,
  `core/permissions.py` (WP3), and `/api/users/agents` (WP7).

## Verification

1. `docker compose build backend` builds the image with the new pins.
2. `docker compose run --rm backend pytest -q` runs all tests (WP1 + new auth tests) and should pass.
3. `docker compose up -d backend` then `curl.exe -s http://localhost:8000/api/health` should still
   report `ok`. The migration runs on start.
4. By hand in `/docs`: register, then paste the token into Authorize, then `GET /api/auth/me`
   returns the user.
