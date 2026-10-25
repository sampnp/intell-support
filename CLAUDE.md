# CLAUDE.md

`docs/PLAN.md` is the specification for this project; work packages (WPs) are listed in its §13.

## Definition of done for every work package

- Copy the approved plan from `~/.code0/plans/<plan-file>.md` into `docs/codezero/plans/`.
- Append an entry for the WP to `docs/CODEZERO_NOTES.md` using the template in that file.
- Run `docker compose run --rm backend pytest -q` and only commit if it passes.
- Commit messages: `WPn: <short summary>`. Never add `Co-Authored-By`, "Generated with",
  or any AI attribution lines to commits or PRs.
- Include the `.code0/` folder in the commit.
- Merge the WP branch into `main` and push both.
