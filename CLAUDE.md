# Northstar, for the next session

Read `AGENTS.md` before changing behavior. Product: `prd.md`. Spec: `docs/spec.md`. Build order: `docs/plans/slice-1-build-phases.md`. This file is only the stop point. It is not a second spec.

Still slice 1. Owner: Malatesha (`PrasannaMalatesha`). No `Co-authored-by` and no tool credits. Do not print or commit `.env`.

## Done

Branch from `origin/dev`. Issues #2–#4 and #6–#21 are closed. `local` and `dev` can read only the `handbook-dev` namespace. The console calls `FASTAPI_URL` or a same-origin path.

## Pending

Close an issue when its acceptance criteria are met.

Still open:

- #22 stays open. Safety code scores every LangGraph trace. The OpenRouter judge scores abstain, escalate, and a 10 percent sample. A specialist edit is not a field on the trace, so that part of the ticket is still unmet.
- #1 stays open while #22 is open. Issues #2–#21 are closed.

Also still unfinished: middleware is not attached, and the screen recording is not done. `PostgresStore` is slice 2. Do not invent deploy hooks. Do not promote `dev` to `uat` or `prod` unless asked. Phase checkboxes stay unchecked except phase 0, unless asked.

## Continue

Branch from `origin/dev`. Push with `git push -u origin HEAD:feature/<name>`. Open the PR into `dev`. Run `uv run pytest` before that PR. Secrets stay in the gitignored `.env`.
