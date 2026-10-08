# Northstar, for the next session

Read `AGENTS.md` before changing behavior. Product: `prd.md`. Spec: `docs/spec.md`. Build order: `docs/plans/slice-1-build-phases.md`. This file is only the stop point. It is not a second spec.

Slices 1 and 2 are done. Owner: Malatesha (`PrasannaMalatesha`). Every commit, PR, issue, and release is authored by Malatesha only. No `Co-authored-by`, no "Made with" footers, no tool credits in commits, PRs, docs, or code. Do not print or commit `.env`.

Canonical docs win over this file when they disagree. Update this file when you stop so the next session can continue.

---

## Where to start

```bash
git fetch origin
git checkout dev
git pull origin dev
```

## Stop point (2026-10-08, before the demo)

Tip of `origin/dev`: the merge of the published-email fix (after PR #104). CI green. Nothing promoted to `uat` or `prod`.

Last session, in order:
1. Slices 1 and 2 were already done and closed. The console walkthrough was re-recorded after PR #98 (local, gitignored, in `apps/web/walkthrough-results/`).
2. Issue #101, closed (PRs #102, #104): the golden dataset and experiments run in LangSmith. `make evals-sync` writes `Northstar Support: E2E` (tags `slice1`, `slice2`) and `Northstar Support: Intent Classifier`. `make evals` (or `uv run python -m evals.experiments run --split test --repetitions 3`) runs v0, v1 (the live desk), and the router with the code checks and the quiz judge. `promote <run_id>` adds a reviewed specialist edit under a new tag.
3. PR #103: desk bugs on policy questions that mention an order, start with "If", end in ", right?", or say "how much"/"price", found by the first v1 experiment. Fixed.
4. PR #104: the judge is `deepseek/deepseek-v4.1-flash` on OpenRouter (key only in `.env`). The offline quiz judge is a majority of three and was recalibrated 5 of 5.
5. The judge found the contact answer showing "[email]": `screen()` masked the handbook's own support address. Fixed with `PUBLISHED_EMAILS`. Live after the fix: test split v1 answer_correct 1.0, label_match 1.0, status 1.0 (v0 label_match 0.733). Router 1.0.
6. A LangSmith online LLM judge (`langsmith_groundedness`, rule "Northstar groundedness (LangSmith judge)") now scores every LangGraph root run in `northstar-local`, beside the in-app judge. The prompt is the whole handbook, rebuilt from `data/policy` by `uv run python -m northstar.online`; rerun it after a handbook change (delete the rule first, it is created once).

Results are in `results/langsmith_test.md` and `results/langsmith_dev.md`.

7. The first specialist edit was promoted (`edit-01a11a09`, "Do you sell surfboard wax?", tag `edit-20261008-054354`, 68 cases). The dev experiment on that version shows the gap: v1 abstains where the specialist said the product is not carried.

Next, only when Malatesha asks: slice 3 (#65), the hand-recorded LangSmith part of the walkthrough, or promoting `dev` → `uat`.

How to run the demo:
- **Servers:** restart any API or console started before PR #98, because they run old code (`make api`, `make web`).
- **Database:** use a fresh one, so old cases and tickets do not trigger duplicate blocks. Set `DATABASE_URL` to a new database. The dry run used `northstar_demo`, with the API on 8020 and the console on 3020 via the untracked `.claude/launch.json`.
- **Two logins at once:** use two hostnames, specialist on `specialist.localhost:3020` and lead on `127.0.0.1:3020`.
- **Pace:** live turns take up to about 10 s.

Demo script, binding Mira Shah (`mira.shah@northstar.example`):
- **Handbook:** "How long does a customer have to return a pair of shoes?" Cited answer.
- **Cancel:** "Please cancel order NS-1004." The lead approves and gets a ticket.
- **Address change:** "New address for order NS-1005: please ship it to 40 Elm Ave, Round Rock TX 78664."
- **Exchange:** "Exchange order NS-1001 for size L." Proposal. Then "Exchange order NS-1006 for size M." Refused, EXC-STOCK.
- **Warranty:** "The desk speaker on order NS-1007 stopped working."
- **Lost package:** "Order NS-1009 never arrived." The lead edits the amount.
- **Gaps list:** "What is your favorite color?" appears in the lead's handbook gaps list.
- **Escalation:** "The website said I have 60 days to return order NS-1001." Escalated, with a handoff packet (owner: policy).
- **Preference:** a new case with "I prefer email. Please refund order NS-1001." The preference and history show, and the amount is unchanged.

`:memory:.ses` (stray, untracked) stays as is, per Malatesha. Do not commit or delete it.

## Done so far

Slice 1 P0 is complete. #22 and #1 are closed. `uat`, `dev`, `prod`, and `main` are protected: a PR is required, `Test API` and `Lint and build console` must pass, admins included, no force pushes. Every change goes through a PR into `dev`.

Slice 2 (P1) is built and merged into `dev` (PRs #85 to #96). Every sub-issue of [#64](https://github.com/PrasannaMalatesha/northstar-support-agent/issues/64) is closed:
- **Gated actions:** one table in `packages/agent/northstar/actions.py` holds cancel, address change, exchange, warranty claim, shipment, and refund. Each has a pure handbook rule. `FAMILIES` is the one source for proposal decisions.
- **Duplicates:** one ticket per order and action family (R15).
- **Lead tools:** the queue with citations and an order summary, plus a read-only case view (R16). The handbook gaps list (R19).
- **Escalation:** the handoff packet with an owner (R17).
- **Edit pairs:** sent to the LangSmith `Northstar specialist edits` queue (R18).
- **Preferences:** contact channel in `PostgresStore` (R20).

Slice 2 labeled desk cases are in `SLICE2_CASES` (`evals/labeled.py`), a new dataset version beside the frozen 40.

Slice 3 ([#65](https://github.com/PrasannaMalatesha/northstar-support-agent/issues/65), sub-issues #78 to #81) is next only when Malatesha asks. Its rule is "after slice 2 is in use". #79 (customer chat) still has no `ready-for-agent` label: `prd.md` must first decide how a customer identifies themselves in the chat. Do not create more tickets unless asked.

Seed orders for demos (customer Mira Shah). Dates hold for the tests' fixed clock (2026-10-06) and a few days after:
- **NS-1001**, wool coat, delivered: refund, exchange to L, defect inside the window.
- **NS-1003**, scarf, already refunded: deny.
- **NS-1004**, kettle, placed: cancel, address change.
- **NS-1005**, tote, packed: no cancel, address change allowed.
- **NS-1006**, rain jacket, out of stock: exchange refused (EXC-STOCK), delivered but not received.
- **NS-1007**, desk speaker, past its return window: warranty claim.
- **NS-1008**, linen shirt: warranty expired.
- **NS-1009**, shipped 2026-09-16 with no delivery: lost, refund proposal.
- **NS-1010**, shipped 2026-10-05: inside the delivery window.

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
| #83 | Built-in middleware on the `create_agent` subgraphs; traces masked by a LangSmith anonymizer |
| #84 | Console walkthrough recording script |
| #85–#97 | Slice 2 (#66 to #77) |
| #98 | Dry-run fixes: stale reply on a paused turn, judge off the request path, edit confirms with the ticket id |

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

- Screen recording: the console part records with `npx playwright test -c playwright.walkthrough.config.ts` (from `apps/web`, fresh database). The LangSmith part (a failed eval and its trace) is recorded by hand.
- Only the `northstar-local` LangSmith project exists. When `northstar-dev`/`uat`/`prod` get traffic, attach the safety rule and the LangSmith groundedness judge with `uv run python -m northstar.online` and that `LANGSMITH_PROJECT`.
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
| `evals/experiments.py` | LangSmith datasets (`sync`), v0/v1/router experiments (`run`), edit promotion (`promote`) |
| `correction.md` | What changed and why |
| `.github/workflows/ci.yml` | Lint, pytest, smoke, axe |

---

## Out of scope until asked

- Creating tickets from slice 2 (P1: `PostgresStore` prefs, queue decide-from-list, R13–R20) or slice 3 (P2).
- Promoting `dev` → `uat` → `prod`.
- Inventing Render/Vercel deploy hooks.
- Screen recording (submission artifact; not a code ticket unless opened).
- `trd.md` (do not write until asked).

---

## Continue checklist

1. `git checkout dev && git pull origin dev`. Confirm `uv run pytest` passes (136 or more).
2. Read the Stop point section above. Ask Malatesha what is next: the demo prep, slice 3 (#65), the LangSmith part of the walkthrough, or promoting `dev` → `uat`.
3. Every change: a `feature/*` branch from `origin/dev`, a PR into `dev`, merged only when CI is green.
4. Rewrite the Stop point section before you stop.
