# Northstar, for the next session

Read `AGENTS.md` before changing behavior. Product: `prd.md`. Spec: `docs/spec.md`. Build order: `docs/plans/slice-1-build-phases.md`. This file is only the stop point. It is not a second spec.

Slices 1, 2, and 3 are done. Owner: Malatesha (`PrasannaMalatesha`). Every commit, PR, issue, and release is authored by Malatesha only. No `Co-authored-by`, no "Made with" footers, no tool credits in commits, PRs, docs, or code. Do not print or commit `.env`.

Canonical docs win over this file when they disagree. Update this file when you stop so the next session can continue.

---

## Where to start

```bash
git fetch origin
git checkout dev
git pull origin dev
```

## Stop point (2026-10-10, end-to-end fixes on dev)

`uat`, `prod`, and `main` hold the conversation fixes (#158 to #160). `dev` is ahead with #161 to #163, not promoted:
- #162: the end-to-end check, `results/e2e_check_2026-10-10.md`.
- #163: its fixes:
  - final sale (a reranker recheck with the model when it drops Pinecone's first section);
  - fraud in any tense;
  - price questions reach the handbook, while item questions stay on the catalog;
  - wrong-item refunds;
  - one order per request;
  - follow-ups read the handbook;
  - nothing changes on a cancelled order;
  - insults and "ignore all previous instructions" get the safe reply;
  - "torn" is a defect;
  - chat order lookups;
  - a consistent NS-1002 seed.

  Details are in `correction.md`.

There are no open issues. 347 Python tests and 12 browser tests pass; run the browser suite on a fresh database. The release bar on #163's code passed every gate (English p95 4.44 s). The next PR into `uat` needs a fresh run on `dev` with its results file committed. Promote only when Malatesha asks.

The browser suite runs on the real clock. NS-1002 stays inside its return window through 2026-10-31, and Mira's orders follow the tests' 2026-10-06 dates. Move the seed dates, or give the browser API a fixed clock, before then.

Suggested next, not started (details in the 2026-10-10 session notes):
- **Token budget.** Each handbook question is charged a flat 1,000 tokens (`TOKENS_PER_TURN`) against a 20,000-a-day budget, so a specialist gets only 20 handbook questions a day. Charge the reported usage, or raise the budget.
- **`TOKEN_CAP`.** It is still the provisional 10,000; the real peak is about 2,200. Suggested 5,000. Also make "Release bar results" a required check on `uat`.
- **The conversation check.** Move the 32-conversation check into `evals` so it can be run again.
- **Google SSO.** It needs OAuth values. Turning it on hides the password form, and only emails in `staff_users` can sign in, so a staff row with a real Google email is needed first.

Open for Malatesha:
- A stronger reranker. The FlashRank MiniLM model scores some plain questions near zero; it needs a model download.
- The LangSmith `update-handover` example `chat-three-failures` still has its old question. Re-sync it when the trace limit allows.

**Update phase** (`prd.md` R34 to R49, `docs/plans/update-phase.md` with "Built differently", ADR `docs/adr/0001-live-chat-line-in-postgres.md`, terms in `CONTEXT.md`, details in `correction.md`):
- Per-customer chat limits in Postgres.
- A 45 s turn deadline.
- The escalations inbox.
- The follow-up after 3 failed turns or a typed "I want a person".
- Live chat behind `LIVE_CHAT_ENABLED` (off by default): the line, offers, the wait estimate, quiet-customer timers, money actions that still wait for a lead, and the lead's line view.
- Experiments sized to the trace budget, plus a release-bar results file checked in CI on PRs into `uat`.

Open for Malatesha:
- Whether the agent answers while an escalation waits in the line (today it stays quiet).
- Making "Release bar results" a required check on `uat`.
- Setting `TOKEN_CAP` from the first real release run.
- A follow-up PR that moves the live chat code out of `cases.py`.
- A "done" state for the escalations inbox.

Browser checks: run them from a worktree, or stop the old `next dev` on port 3000 first. It shares `apps/web/.next`, and the cache corrupts.

What exists now, beyond slices 1 and 2:
- **LangSmith evals (#101):** `make evals-sync` writes `Northstar Support: E2E` (tags `slice1` 40, `slice2` 67, `edit-20261008-054354` 68, `slice3-es` 74, `slice3-photo` 77) and `Northstar Support: Intent Classifier` (14). `uv run python -m evals.experiments run --split test --repetitions 3` runs v0, v1 (the live desk), and the router; `--version <tag>` limits to one version's cases; results go to `results/langsmith_<split>[_<version>].md`. `promote <run_id> --decision ... --sections ...` adds a reviewed specialist edit under a new tag (one done: the surfboard-wax case).
- **Judges:** `deepseek/deepseek-v4.1-flash` on OpenRouter (key only in `.env`, also a LangSmith workspace secret for the rule). The offline quiz judge is a majority of three, calibrated 5 of 5. Three online checks on `northstar-local`: the `safety` code rule, the LangSmith LLM judge rule (`langsmith_groundedness`, prompt rebuilt from `data/policy` by `uv run python -m northstar.online`; delete the rule first to rebuild), and the in-app sampled judge (`policy_groundedness`).
- **Fixes the experiments found:** policy questions that mention an order or start with "If" (#103); the masked support address (`PUBLISHED_EMAILS`, #105); "do you sell" now asks the catalog (#108).
- **Slice 3:** #81 Spanish (`northstar/language.py`, #114); #80 damaged-item photo and the REF-DAMAGED rule (`northstar/photo.py`, seed order NS-1011, #112); #79 customer chat (`/chat`, order id plus order email, chat token audience `northstar-chat`, cases owned by the disabled `chat@northstar.example`, #113; decision in `prd.md`); #78 Google SSO (`POST /auth/sso`, role from `staff_users`, #115).
- **Trace upload off the request (#116):** a turn no longer waits for LangSmith.
- **End-to-end check (2026-10-08):** the whole demo script below was driven in a browser against fresh servers and a fresh database. Every step behaved as intended. It found one bug, fixed in #121: after an escalation the customer chat was locked for good, and a chat message sent while a request waited was dropped silently. Now the next message after an escalation starts a new chat case, and a waiting request gets a reason. The desk tool error that `ToolErrorMiddleware` catches is now logged: one turn in about 35 showed "The lookup failed" with no log, and it did not come back in 30+ retries.

Waiting on Malatesha:
- **Google SSO is off** until `AUTH_GOOGLE_ID` and `AUTH_GOOGLE_SECRET` are in `.env` (redirect URI `http://localhost:3000/api/auth/callback/google`). A real Google sign-in has not been tried yet.
- **LangSmith hit its monthly unique-trace limit** (429, 2026-10-08). New traces, rule scores, judge feedback, and experiments are dropped until the 2026-11-01 reset or a raised limit. The app is unaffected.
- **Demo:** after slice 3, as decided. Restart servers on a fresh database first.

Keep: every LangSmith experiment (do not delete). `:memory:.ses` stays untracked. The old branch `feature/spanish-replies` is superseded by #114 and was left in place.

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
- **Damaged-item photo:** "The desk lamp on order NS-1011 arrived damaged." with `evals/photos/lamp-cracked.png` attached. REF-DAMAGED proposal; the lead sees "Photo: visible damage."
- **Spanish:** "¿Cuántos días tengo para devolver unos zapatos?" Spanish answer citing REF-CATEGORY.
- **Customer chat:** open `/chat`, order NS-1006 with `mira.shah@northstar.example`, then "Please refund order NS-1006." The customer sees "Nothing is approved yet"; the lead's queue has the proposal.

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

Slice 3 ([#65](https://github.com/PrasannaMalatesha/northstar-support-agent/issues/65), sub-issues #78 to #81) is done and closed. The update phase (spec #131, tickets #132 to #145) is done and closed. It is promoted to every branch. Do not create more tickets unless asked.

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

No open issues. Slices 1 (#1), 2 (#64), and 3 (#65) and #101 are closed.

Unfinished work, not GitHub tickets unless Malatesha opens them:

- Screen recording: the console part records with `npx playwright test -c playwright.walkthrough.config.ts` (from `apps/web`, fresh database). The LangSmith part (a failed eval and its trace) is recorded by hand.
- Only the `northstar-local` LangSmith project exists. When `northstar-dev`/`uat`/`prod` get traffic, attach the safety rule and the LangSmith groundedness judge with `uv run python -m northstar.online` and that `LANGSMITH_PROJECT`.
- Turns that end before the graph (request limit, secret block, slur/jailbreak block) have no LangGraph trace. That is by design: a deterministic block ends before any model call.
- `:memory:.ses` in the repo root is a stray untracked file. Malatesha asked to keep it for now. Do not commit or delete it.

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

- Creating new tickets.
- Promoting `dev` → `uat` → `prod` → `main`.
- Inventing Render/Vercel deploy hooks.
- Screen recording (submission artifact; not a code ticket unless opened).
- `trd.md` (do not write until asked).

---

## Continue checklist

1. `git checkout dev && git pull origin dev`. Confirm `uv run pytest` passes (347 or more).
2. Read the Stop point section above. Ask Malatesha what is next: the demo, turning on Google SSO, the LangSmith limit, or new work. Do not create tickets or promote branches unless asked.
3. Every change: a `feature/*` branch from `origin/dev`, a PR into `dev`, merged only when CI is green.
4. Rewrite the Stop point section before you stop.
