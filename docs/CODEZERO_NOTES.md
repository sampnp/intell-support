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

Screenshots live in `docs/screenshots/codezero/`.

---

## Entry template

```
### WPn — <title>   (YYYY-MM-DD)
- Mode:
- Prompt:
- Plan summary:
- Changes I made to the plan before approving (and why):
- What was generated:
- Issues found in review / tests (and how they were fixed):
- Verification (tests run, mutation check, manual check):
- Screenshots:
- Time taken:
```

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


---

## Summary (written at the end)

- Where CodeZero helped most:
- Where its output was wrong or needed correction:
- How generated code was verified:
- What I would do differently:
