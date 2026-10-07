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

PR #61 (edit judge, handoff through the graph) is merged. The fix that writes the judge score to the LangGraph root is on `feature/judge-root-run`. Then:

1. Merge `feature/judge-root-run` if its PR is still open and green.
2. #22 box "a miss blocks promotion to uat" is **not met**. `uat` (and `dev`, `prod`, `main`) have no branch protection and the repo has no rulesets, so a red CI does not block a merge into `uat`. AGENTS.md asks for protection on all four. The fix is a GitHub setting: require the `Test API` and `Lint and build console` checks on `uat`. Only do this with Malatesha's go-ahead.
3. After that, close #22, then #1.
4. Update this file before you stop.

Do not invent deploy hooks. Do not promote `dev` → `uat` or `prod` unless Malatesha asks. Do not create tickets from slice 2 / P1 or slice 3 / P2 unless asked. Phase checkboxes in `docs/plans/slice-1-build-phases.md` stay unchecked except phase 0, unless asked. `PostgresStore` is slice 2.

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
| `feature/judge-root-run` | The judge writes to the LangGraph root, not a child model call (bug found on a live turn) |

#57 was closed unmerged, because #60 replaced it.

How the online path works now:

- `run_turn` sets the LangGraph root run id up front (`config["run_id"]`, a uuid7) and returns it on `Draft.run_id`. `CaseStore._save` stores it in `case_messages.run_id` (null when tracing is off, including in pytest).
- `CaseStore.close` (resolve or escalate) judges the last turn when `final_text` differs from the draft. `CaseStore.edit_amount` judges the proposal turn when the lead changes the amount. Both call `record_judge(..., edited=True)` on the stored run id and skip when the run id is null.
- Handoff escalations (`ESC-LEGAL`, `ESC-WHEN`) run through `run_turn` with the handoff as the fixed desk draft, so they get a root run with `decision = escalate`.
- The sampling rule lives only in `northstar.online.should_judge`. `evals.release_bar.online_checks` imports it.
- Tests: `apps/api/tests/test_edit_judge.py` (fake grader and fake feedback writer, no live calls).

---

## Still open

| Issue | Title | Status |
| --- | --- | --- |
| [#22](https://github.com/PrasannaMalatesha/northstar-support-agent/issues/22) | The release bar and an axe pass gate uat | **OPEN** — uat branch protection missing (see Where to start) |
| [#1](https://github.com/PrasannaMalatesha/northstar-support-agent/issues/1) | Spec: Northstar Support Agent, slice 1 | **OPEN** — close only after #22 |

### #22 acceptance (from the issue)

- [x] Action correct ≥ 80% on the held-out set (`test_the_held_out_set_meets_the_release_bar`, CI).
- [x] Zero tickets without approval. Zero invalid citations. Every abstain row abstains (release bar, CI).
- [x] p95 turn latency under 10s excluding approval wait; no token cap exceeded (release bar, CI).
- [x] Login, case desk, waiting list: axe scan + keyboard walkthrough (`apps/web/tests/screens.spec.ts`, CI).
- [ ] A miss blocks promotion to uat. CI fails on a miss and the Deploy job `needs` it, but nothing blocks the merge into `uat`. Needs branch protection with required checks.
- [x] Online checks: safety code on every LangGraph run; judges cover a sample plus every abstain, escalation, and edit. Checked live on `northstar-local` 2026-10-07: `safety = 1` from the run rule and `policy_groundedness = 1` from the judge, both on the LangGraph root. Only `northstar-local` exists in LangSmith. When `northstar-dev`/`uat`/`prod` get traffic, run `uv run python -m northstar.online` with that `LANGSMITH_PROJECT` to attach the rule.

Also unfinished (not separate GitHub tickets unless you open them):

- Built-in LangChain middleware is not fully wired on the `create_agent` subgraphs (PII, HITL, call limits, etc. per `AGENTS.md`).
- Screen recording for the submission walkthrough is not done.
- Turns that end before the graph (request limit, secret block, slur/jailbreak block) have no LangGraph trace. That is by design: a deterministic block ends before any model call.
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

1. Sync `dev`. Merge `feature/judge-root-run` if its PR is still open and green.
2. With Malatesha's go-ahead, protect `uat` with the required checks `Test API` and `Lint and build console` (AGENTS.md also asks for `dev`, `prod`, `main`).
3. Close #22, then #1.
4. Next work only when asked: middleware wiring, then the screen recording.
5. Rewrite the Where to start / Still open sections of this file for the next stop.
