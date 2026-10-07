# Northstar, for the next session

Read `AGENTS.md` before changing behavior. Product: `prd.md`. Spec: `docs/spec.md`. Build order: `docs/plans/slice-1-build-phases.md`. This file is only the stop point. It is not a second spec.

Still slice 1. Owner: Malatesha (`PrasannaMalatesha`). No `Co-authored-by` and no tool credits. Do not print or commit `.env`.

## Done

Desk behavior for GitHub issues #2–#22 is on `dev` through the merge of PR #49 (`fe57dff`). A refund proposal now pauses the graph thread with `interrupt` until a lead approves, edits, or rejects. The case row is still the ticket.

## Pending

- `support_agent` and `refund_agent` are plain nodes. Use `create_agent` when the model must choose tools.
- No LLM pairwise run. `results/v0_v1.md` is label match only.
- `PostgresStore` is slice 2.
- Deploy hooks are unset. Do not invent them. Do not promote `dev` to `uat` or `prod` unless asked.
- Phase checkboxes stay unchecked except phase 0, unless asked.
- Do not close issue #1 unless asked. Do not recreate issues #2–#22.
- Screen recording is not done.

## Continue

Branch from `origin/dev`. Push with `git push -u origin HEAD:feature/<name>`. Open the PR into `dev`. Run `uv run pytest` before that PR. Secrets stay in the gitignored `.env`.
