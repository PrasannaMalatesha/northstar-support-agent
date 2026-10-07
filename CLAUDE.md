# Northstar, for the next session

Read `AGENTS.md` before changing behavior. Product: `prd.md`. Spec: `docs/spec.md`. Build order: `docs/plans/slice-1-build-phases.md`. This file is only the stop point. It is not a second spec.

Still **slice 1** (P0). Owner: Malatesha (`PrasannaMalatesha`). Every commit, PR, issue, and release is authored by Malatesha only. No `Co-authored-by`, no "Made with" footers, no tool credits in commits, PRs, docs, or code. Do not print or commit `.env`.

Canonical docs win over this file when they disagree. Update this file when you stop so the next session can continue.

---

## Where to start

```bash
git fetch origin
git checkout dev
git pull origin dev
```

Slice 1 P0 is complete. #22 and #1 are closed. `uat`, `dev`, `prod`, and `main` are protected: a PR is required, `Test API` and `Lint and build console` must pass, admins included, no force pushes. Every change goes through a PR into `dev`.

Slice 2 and slice 3 tickets exist:

- [#64](https://github.com/PrasannaMalatesha/northstar-support-agent/issues/64) Spec, slice 2 (P1, R13 to R20). Sub-issues #66 to #77.
- [#65](https://github.com/PrasannaMalatesha/northstar-support-agent/issues/65) Spec, slice 3 (P2). Sub-issues #78 to #81. Blocked by #64: slice 3 starts only after slice 2 is in use.

Start with any slice 2 ticket that has no open blocker. #66 (a gated proposal carries any action) unblocks #68, #69, #70, #71, #72, #74, #75. #67, #73, #76, #77 can start now. #79 (customer chat) has no `ready-for-agent` label: `prd.md` must first decide how a customer identifies themselves in the chat. Do not create more tickets unless asked.

Do not invent deploy hooks. Do not promote `dev` → `uat` or `prod` unless Malatesha asks. Phase checkboxes in `docs/plans/slice-1-build-phases.md` stay unchecked except phase 0, unless asked. `PostgresStore` is slice 2.

---

## Done (do not redo)

Issues **#2–#21** are closed on GitHub. Desk, auth, cases, orders, catalog, refund HITL, guardrails path, labeled set, release bar, axe, namespace guard, citation guard, live safety rule, sampled groundedness judge, and the edit judge are in.

| PR | What landed |
| --- | --- |
| #56 | `local`/`dev` read only `handbook-dev`; console uses `FASTAPI_URL` or same-origin |
| #58 | Bad citation → abstain before save |
| #59 | Safety code on every LangGraph root run; OpenRouter groundedness on abstain / escalate / 10% sample |
| #60 | Handoff notes for #22 (this file) |
| #61 | Judge every edited draft or amount; handoff escalations run through the graph; one sampling rule |
| #62 | The judge writes to the LangGraph root, not a child model call (bug found on a live turn) |

#57 was closed unmerged, because #60 replaced it.

How the online path works now:

- `run_turn` sets the LangGraph root run id up front (`config["run_id"]`, a uuid7) and returns it on `Draft.run_id`. `CaseStore._save` stores it in `case_messages.run_id` (null when tracing is off, including in pytest).
- `CaseStore.close` (resolve or escalate) judges the last turn when `final_text` differs from the draft. `CaseStore.edit_amount` judges the proposal turn when the lead changes the amount. Both call `record_judge(..., edited=True)` on the stored run id and skip when the run id is null.
- Handoff escalations (`ESC-LEGAL`, `ESC-WHEN`) run through `run_turn` with the handoff as the fixed desk draft, so they get a root run with `decision = escalate`.
- The sampling rule lives only in `northstar.online.should_judge`. `evals.release_bar.online_checks` imports it.
- Tests: `apps/api/tests/test_edit_judge.py` (fake grader and fake feedback writer, no live calls).

---

## Still open

No open slice 1 issues. #22 closed after branch protection made a CI miss block the merge into `uat`. #1 closed after #22.

Unfinished work, not GitHub tickets unless Malatesha opens them:

- Built-in LangChain middleware is not fully wired on the `create_agent` subgraphs (PII, HITL, call limits, etc. per `AGENTS.md`).
- Screen recording for the submission walkthrough is not done.
- Only the `northstar-local` LangSmith project exists. When `northstar-dev`/`uat`/`prod` get traffic, attach the safety rule with `uv run python -m northstar.online` and that `LANGSMITH_PROJECT`.
- Turns that end before the graph (request limit, secret block, slur/jailbreak block) have no LangGraph trace. That is by design: a deterministic block ends before any model call.
- `:memory:.ses` in the repo root is a stray untracked file. Malatesha asked to keep it for now. Do not commit or delete it.
- Do not start slice 2.

---

## Workflow (non-negotiable)

- Branch from `origin/dev`. Push `git push -u origin HEAD:feature/<name>`. PR base is always `dev`.
- Run `uv run pytest` before the PR. Fix failures; do not skip hooks.
- Close a GitHub issue only when its acceptance criteria are met. If one criterion remains, leave the issue open and say why in `correction.md` / this file.
- Secrets stay in gitignored `.env`. Never commit them.
- Prefer short diffs. One feature lives in one module. New stores or evaluators are adapters behind ports when the contract requires it.
- Official LangChain / LangGraph / LangSmith docs win on API details. Cite the URL in `architecture.md` or `correction.md` when you change approach.

---

## Key files

| Path | Role |
| --- | --- |
| `AGENTS.md` | Contract |
| `prd.md` | Product requirements |
| `docs/spec.md` | Slice 1 implementation spec |
| `docs/plans/slice-1-build-phases.md` | Phase order (only phase 0 checked) |
| `packages/agent/northstar/online.py` | Safety rule, live judge, the one sampling rule (`should_judge`) |
| `packages/agent/northstar/graph.py` | Router; calls `record_judge` |
| `packages/agent/northstar/cases.py` | Cases, proposals, edit amount |
| `apps/api/northstar_api/main.py` | FastAPI routes including `/approvals/.../edit` |
| `evals/release_bar.py` | Release bar / online check helpers |
| `correction.md` | What changed and why |
| `.github/workflows/ci.yml` | Lint, pytest, smoke, axe |

---

## Out of scope until asked

- Creating tickets from slice 2 (P1: `PostgresStore` prefs, queue decide-from-list, R13–R20) or slice 3 (P2).
- Promoting `dev` → `uat` → `prod`.
- Inventing Render/Vercel deploy hooks.
- Screen recording (submission artifact; not a code ticket unless opened).
- Full middleware attach (follow-up after #22 unless Malatesha prioritizes it).
- `trd.md` (do not write until asked).

---

## Continue checklist

1. Sync `dev`.
2. Pick a slice 2 ticket from the frontier above (start with #66), or ask Malatesha about middleware wiring, the screen recording, or promoting `dev` → `uat`.
3. Rewrite the Where to start / Still open sections of this file for the next stop.
