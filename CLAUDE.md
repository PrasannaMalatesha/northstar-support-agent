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

The specialist-edit judge and the handoff fix are on branch `feature/specialist-edit-judge` (PR into `dev`). If that PR is merged, `origin/dev` holds all slice 1 code that is planned. Then:

1. Ask Malatesha whether #22 may close. Every checklist box is built or covered by CI except "a miss blocks promotion to uat", which stays manual (see below).
2. If yes, close #22 and then #1.
3. Update this file before you stop.

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
| `feature/specialist-edit-judge` | Judge every edited draft or amount; handoff escalations run through the graph; one sampling rule |

#57 was closed unmerged, because #60 replaced it.

How the online path works now:

- `run_turn` returns the LangGraph root run id on `Draft.run_id`. `CaseStore._save` stores it in `case_messages.run_id` (null when tracing is off, including in pytest).
- `CaseStore.close` (resolve or escalate) judges the last turn when `final_text` differs from the draft. `CaseStore.edit_amount` judges the proposal turn when the lead changes the amount. Both call `record_judge(..., edited=True)` on the stored run id and skip when the run id is null.
- Handoff escalations (`ESC-LEGAL`, `ESC-WHEN`) run through `run_turn` with the handoff as the fixed desk draft, so they get a root run with `decision = escalate`.
- The sampling rule lives only in `northstar.online.should_judge`. `evals.release_bar.online_checks` imports it.
- Tests: `apps/api/tests/test_edit_judge.py` (fake grader and fake feedback writer, no live calls).

---

## Still open

| Issue | Title | Status |
| --- | --- | --- |
| [#22](https://github.com/PrasannaMalatesha/northstar-support-agent/issues/22) | The release bar and an axe pass gate uat | **OPEN** — waiting on Malatesha to approve closing it |
| [#1](https://github.com/PrasannaMalatesha/northstar-support-agent/issues/1) | Spec: Northstar Support Agent, slice 1 | **OPEN** — close only after #22 |

### #22 acceptance (from the issue)

- [x] Action correct ≥ 80% on the held-out set (`test_the_held_out_set_meets_the_release_bar`, CI).
- [x] Zero tickets without approval. Zero invalid citations. Every abstain row abstains (release bar, CI).
- [x] p95 turn latency under 10s excluding approval wait; no token cap exceeded (release bar, CI).
- [x] Login, case desk, waiting list: axe scan + keyboard walkthrough (`apps/web/tests/screens.spec.ts`, CI).
- [ ] A miss blocks promotion to uat. Manual: no deploy hooks are invented (same rule that closed #5).
- [x] Online checks: safety code on every LangGraph run; judges cover a sample plus every abstain, escalation, and edit.

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

1. Sync `dev`. Merge `feature/specialist-edit-judge` if its PR is still open and green.
2. Ask Malatesha whether #22 may close with the uat-promotion box left manual.
3. If yes, close #22, then #1.
4. Next work only when asked: middleware wiring, then the screen recording.
5. Rewrite the Where to start / Still open sections of this file for the next stop.
