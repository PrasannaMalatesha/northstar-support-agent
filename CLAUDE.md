# Northstar, for the next session

Read `AGENTS.md` before changing behavior. Product: `prd.md`. Spec: `docs/spec.md`. Build order: `docs/plans/slice-1-build-phases.md`. This file is only the stop point. It is not a second spec.

Still slice 1. Owner: Malatesha (`PrasannaMalatesha`). No `Co-authored-by` and no tool credits. Do not print or commit `.env`.

## Done

Branch from `origin/dev`. Issues #2–#4 and #6–#21 are closed. Their acceptance criteria are met on `dev`.

## Pending

Close an issue when its acceptance criteria are met. Do not leave a finished issue open.

Still open:

- #5 The waking screen and login are in the console. There is no dev deployment, so the console does not yet talk only to the dev API, database, and handbook namespace. Do not invent deploy hooks.
- #22 The held-out release bar and the axe scan run in CI. Online judges are not attached to live LangSmith runs.
- #1 stays open while #5 and #22 are open.

Also still unfinished, and not their own issues: middleware is not attached, and the screen recording is not done. `PostgresStore` is slice 2. Do not promote `dev` to `uat` or `prod` unless asked. Phase checkboxes stay unchecked except phase 0, unless asked.

## Continue

Branch from `origin/dev`. Push with `git push -u origin HEAD:feature/<name>`. Open the PR into `dev`. Run `uv run pytest` before that PR. Secrets stay in the gitignored `.env`.
