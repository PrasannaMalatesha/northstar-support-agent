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

Tip of `origin/dev` after the last merged work: `fa919c6` (PR #59 online judge). Then:

1. Merge or rebase any open doc PRs into `dev` if they are still open (see Open PRs below).
2. Cut `feature/<short-name>` from `origin/dev`.
3. Implement the **#22 specialist-edit** gap (see Next ticket).
4. `uv run pytest` before opening the PR.
5. `git push -u origin HEAD:feature/<name>` and open a PR into `dev`.
6. When CI is green, merge into `dev`. Close the issue only when its acceptance criteria are met.
7. Update this file before you stop.

Do not invent deploy hooks. Do not promote `dev` → `uat` or `prod` unless Malatesha asks. Do not create tickets from slice 2 / P1 or slice 3 / P2 unless asked. Phase checkboxes in `docs/plans/slice-1-build-phases.md` stay unchecked except phase 0, unless asked. `PostgresStore` is slice 2.

---

## Done (do not redo)

Issues **#2–#21** are closed on GitHub. Desk, auth, cases, orders, catalog, refund HITL, guardrails path, labeled set, release bar, axe, namespace guard, citation guard, live safety rule, and sampled groundedness judge are in.

Recent merged PRs (context, not work left):

| PR | What landed |
| --- | --- |
| #56 | `local`/`dev` read only `handbook-dev`; console uses `FASTAPI_URL` or same-origin |
| #58 | Bad citation → abstain before save |
| #59 | Safety code on every LangGraph root run; OpenRouter groundedness on abstain / escalate / 10% sample |

Online eval code lives in `packages/agent/northstar/online.py`. Graph calls `record_judge` from `packages/agent/northstar/graph.py`. Correction note: `correction.md` (online safety + judge section).

Release bar and axe already gate CI (`.github/workflows/ci.yml`). That part of #22 is already built; the issue stays open for the unmet sampling criterion only.

---

## Still open

| Issue | Title | Status |
| --- | --- | --- |
| [#22](https://github.com/PrasannaMalatesha/northstar-support-agent/issues/22) | The release bar and an axe pass gate uat | **OPEN** — last real ticket |
| [#1](https://github.com/PrasannaMalatesha/northstar-support-agent/issues/1) | Spec: Northstar Support Agent, slice 1 | **OPEN** — close only after #22 |

### #22 acceptance (from the issue)

- [ ] Action correct ≥ 80% on the held-out set.
- [ ] Zero tickets without approval. Zero invalid citations. Every abstain row abstains.
- [ ] p95 turn latency under 10s excluding approval wait; no token cap exceeded.
- [ ] Login, case desk, waiting list: axe scan + keyboard walkthrough.
- [ ] A miss blocks promotion to uat.
- [ ] Online checks: safety code on every run; judges cover a sample **plus every abstain, escalation, and specialist edit**.

What is already true on `dev`:

- Safety code evaluator `northstar-safety` attached via run rule `Northstar safety` to every root run named `LangGraph` (sampling rate 1). Attach script: `uv run python -m northstar.online` (needs LangSmith env).
- Live groundedness judge when `decision in {abstain, escalate}` or random sample &lt; 0.1. Feedback key: `policy_groundedness`.

What is **not** true yet (the reason #22 stays open):

- A **specialist edit is not a field on the LangGraph trace**, so the online judge cannot select those runs. `record_judge` / `_should_judge` in `online.py` only know `decision` and the random sample.

Also unfinished (not separate GitHub tickets unless you open them):

- Built-in LangChain middleware is not fully wired on the `create_agent` subgraphs (PII, HITL, call limits, etc. per `AGENTS.md`).
- Screen recording for the submission walkthrough is not done.
- Do not start slice 2.

---

## Next ticket (implement this)

**Close the #22 gap: specialist-edit → judge sample.**

Intent of the unmet criterion: when a specialist edits a draft (or an amount that changes the customer-facing outcome), that run must get the groundedness judge the same way abstain and escalate do.

Suggested shape (shortest correct path; do not invent a second online system):

1. Find where the console/API saves a specialist draft edit or lead amount edit.
   - Lead amount edit: `POST /approvals/{case_id}/edit` in `apps/api/northstar_api/main.py` → `cases.edit_amount`.
   - Specialist draft edit: check case/message routes and PRD R18 / experience notes — store before/after if that path exists; if draft edit is not persisted yet for P0, put a clear `specialist_edit` (or equivalent) flag on the **root run metadata** of the turn that produced the draft being edited, or create a small feedback/annotation path that still triggers `record_judge`. Prefer tagging the existing LangGraph root run over inventing a parallel evaluator.
2. Expose a boolean the online path can read (e.g. run metadata `specialist_edit=true`, or a state field copied into root outputs/metadata).
3. Extend `_should_judge` in `packages/agent/northstar/online.py` so specialist edit is always judged (alongside abstain / escalate / 10% sample). Keep the same `policy_groundedness` feedback key.
4. Mirror the rule in `evals/release_bar.py` online checks if that file documents the same sampling rule (keep one source of truth; do not drift).
5. Unit test with a fake grade/post (pattern already used around `record_judge`). No live OpenRouter call in CI.
6. Record the approach and any doc URL in `correction.md`. Update this file when done.
7. Open PR into `dev`. After merge, if #22 criteria are all met (or Malatesha waives the remaining checklist boxes that are already covered by CI), close #22, then close #1.

Do not invent uat deploy hooks to “satisfy” the miss-blocks-promotion checkbox. That stays manual / out of scope unless asked (same rule that closed #5 without inventing hooks).

---

## Open PRs (doc-only; merge if still open)

| PR | Branch | Purpose |
| --- | --- | --- |
| [#60](https://github.com/PrasannaMalatesha/northstar-support-agent/pull/60) | `feature/issue-22-note` | Notes why #22 stays open after the live judge |
| [#57](https://github.com/PrasannaMalatesha/northstar-support-agent/pull/57) | `feature/issue-5-closed` | Records that #5 is closed |

These are handoff/doc PRs. Merge them into `dev` when green; they are not the specialist-edit implementation.

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
| `packages/agent/northstar/online.py` | Safety rule + live judge |
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
2. Merge open doc PRs #57 / #60 if still open.
3. Implement specialist-edit → online judge for #22.
4. Pytest + PR into `dev` + merge when green.
5. Close #22 if criteria met; then close #1.
6. Rewrite the Pending / Continue sections of this file for the next stop.
