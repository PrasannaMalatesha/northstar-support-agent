# Northstar, for the next session

Read `AGENTS.md` before changing behavior. Product: `prd.md`. Spec: `docs/spec.md`. Build order: `docs/plans/slice-1-build-phases.md`. This file is only the stop point. It is not a second spec.

Still slice 1. Owner: Malatesha (`PrasannaMalatesha`). No `Co-authored-by` and no tool credits. Do not print or commit `.env`.

## Done

Branch from `origin/dev`. Desk behavior for GitHub issues #2–#22 is on `dev`. [PR #50](https://github.com/PrasannaMalatesha/northstar-support-agent/pull/50) pauses a refund proposal on the graph thread with `interrupt` until a lead approves, edits, or rejects. The case row is still the ticket. The pairwise judge preferred v1 on the four held-out desk rows and tied the identical handbook replies (`results/v0_v1.md`). A live turn with `GOOGLE_API_KEY` asks `create_agent`; the desk tool still decides. Pytest keeps the direct call.

## Pending

- The agent is invoked inside the node. Mount it as a subgraph when the trajectory must list the inner tool. Middleware is not attached.
- `evaluate_comparative` still needs two uploaded experiments. The recorded pairwise run is the same judge locally.
- `PostgresStore` is slice 2.
- Deploy hooks are unset. Do not invent them. Do not promote `dev` to `uat` or `prod` unless asked.
- Phase checkboxes stay unchecked except phase 0, unless asked.
- Do not close issue #1 unless asked. Do not recreate issues #2–#22.
- Screen recording is not done.

## Continue

Branch from `origin/dev`. Push with `git push -u origin HEAD:feature/<name>`. Open the PR into `dev`. Run `uv run pytest` before that PR. Secrets stay in the gitignored `.env`.
