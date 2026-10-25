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

---

## Summary (written at the end)

- Where CodeZero helped most:
- Where its output was wrong or needed correction:
- How generated code was verified:
- What I would do differently:
