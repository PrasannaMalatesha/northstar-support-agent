# Corrections

Log approach changes, bugs, and how they were pinned down. Add an entry when the approach changes or a defect is found. Do not delete old entries.

Format:

```
## YYYY-MM-DD — short title
Status: decision | bug | open
What changed or broke:
Evidence:
Debug steps:
Fix:
```

## 2026-10-07 — Policy questions that mention an order were refused or sent to the wrong path

Status: bug

What broke: Through the desk, handbook questions failed in three ways. With no customer bound, any question with the word "order" got "Pick a customer first" (R29 applied to "the same order", "each order line", "after the order is placed"). A question starting with "If" or ending in ", right?" that said "refund" or "return" was read as a refund request and got "Which order id?". "How much is standard shipping?" hit the catalog phrases and got "I don't have that item in the catalog" (the "price" quirk was the same bug).

Evidence: The first LangSmith v1 experiment (issue #101) missed duplicate-hold, one-exchange, one-promo, shipping-price, and wrong-item in all three repetitions. A new test that sends every handbook row through the desk with no customer also missed gift-return.

Debug steps: Traced each miss to its rule. `_asks_for_an_order` matched the bare word. `_POLICY_QUESTION` only knew questions that start with can, how, what, and similar. `_catalog_draft` abstained on "how much" or "price" even when no catalog item was named.

Fix: An order question is now a particular order ("my order", "order 1001"); R29 still blocks those. `_POLICY_QUESTION` also accepts "If ...?" and "..., right?". With no item named, the catalog steps aside when a handbook section answers. Test: `test_handbook_rows_answer_the_same_through_the_desk_with_no_customer`.

Live result after the fix, code checks only (`results/langsmith_test.md`, `results/langsmith_dev.md`): test split v1 `label_match` 1.0 over 3 repetitions (was 0.667), v0 0.733. Dev split with the slice 2 cases (tag `slice2`, 42 cases) v1 1.0, v0 0.333. Citations 1.0 and case status 1.0 on both.

## 2026-10-07 — The golden dataset and the v0-to-v1 experiments now run in LangSmith (issue #101)

Status: bug

What broke: `AGENTS.md` asks for the golden dataset, `aevaluate` experiments, and edit pairs promoted into a new dataset version. Only the local half existed: the labeled cases, pytest checks, and `results/*.md`. LangSmith had traces and feedback but no dataset and no experiment.

Evidence: `Client().list_datasets()` returned nothing. No code called `evaluate` or `create_examples`.

Debug steps: Checked each live piece before building: the judge key graded a right and a wrong answer correctly, Pinecone retrieved REF-CATEGORY, and LangSmith held `policy_groundedness`, `safety`, and `specialist_edit` feedback from live turns.

Fix: `evals/experiments.py`.
- `sync` writes `Northstar Support: E2E` (the 40 frozen cases tagged `slice1`, plus the slice 2 cases tagged `slice2`) and `Northstar Support: Intent Classifier` (hand-labeled routes in `INTENT_CASES`). Example ids come from the case id, so a second sync adds nothing.
- `run` evaluates v0 (the handbook answerer) and v1 (the desk through the API, live agent model and Pinecone, one case at a time) on one split and tag, with `label_match`, `citation_valid`, `status_correct`, and the calibrated quiz judge `answer_correct` on handbook rows. The router gets its own experiment with `correct`. It uses `client.evaluate`, the sync form, because the desk target is synchronous ([evaluate a complex agent](https://docs.langchain.com/langsmith/evaluate-complex-agent)).
- `promote` adds one reviewed specialist edit as a labeled case under a new tag. A person picks the decision and sections. Nothing is added automatically.
- The first run hung on a judge call with no timeout, and the app's sampled online judge ran on every experiment turn and competed for the free judge model. The judge now has a 60 s timeout, retries, and an `InMemoryRateLimiter` ([rate limits](https://docs.langchain.com/langsmith/handle-model-rate-limiting)). The experiment harness turns the online judge off. The free model sometimes returns no choices, so `answer_correct` tries three times.
- The OpenRouter key then hit its free daily cap (`free-models-per-day`, 50 requests, reset 2026-10-08 19:00 CDT). Until it resets or credits are added, the quiz judge and the live groundedness judge both fail; the live one only logs. `run --no-judge` scores with the code checks alone, and the judge scores are added by a later `run` once the key has quota.

First LangSmith result (test split, tag `slice1`, 3 repetitions, code checks only; full list in `results/langsmith_test.md`):
- v0 `label_match` 0.733, v1 0.667. Citations valid 1.0 for both. v1 case status 1.0. Router `correct` 1.0 on 14 rows. The same misses in all three repetitions.
- v1 sends handbook questions through the real desk. The earlier local comparison (`results/v0_v1.md`) sent them to the handbook answerer, so it hid this.
- Fixed in the next entry. With no customer bound, a policy question that mentions "order" gets `unbound` (duplicate-hold, one-exchange, one-promo). shipping-price hits the known "price" catalog quirk. wrong-item gets `ask_clarification`. These are desk routing bugs, recorded here as honest failures.

## 2026-10-07 — An amount edit now confirms with the ticket id

Status: bug

What broke: Approve sent the lead back to the desk with "Ticket <id>". Edit amount also records a ticket, but went back to the plain desk with no confirmation (the PRD's Peak-End rule asks for one).

Evidence: Browser dry run: the lead edited 4800 to 4000 cents and saw only "No proposal is waiting."

Debug steps: Read the edit server action. It ignored the API's `ticket_id`.

Fix: The edit action redirects to `/desk?ticket=<id>`, the same as approve. Checked in the browser (12800 edited to 6400, "Ticket ..." shown). The desk page.

## 2026-10-07 — The live judge made a sampled turn wait a minute

Status: bug

What broke: In the browser dry run, a cancel took more than a minute to come back. The groundedness judge ran inside the request. The free OpenRouter judge model sends its response headers at once (that is when httpx logs 200) and then takes up to a minute to write the body. Every sampled turn (abstain, escalate, an edit, or the 10 percent sample) made the specialist wait for it, which also breaks the 10-second p95 release bar for live traffic. The same script outside the server ran the turn in 2.9 seconds, because that turn was not sampled.

Evidence: The API log showed Gemini, then OpenRouter 200, then the `POST /cases/current/messages` line about a minute later. `pg_stat_activity` showed no lock waits.

Debug steps: Reproduced the turn in a script with `faulthandler.dump_traceback_later`. That turn was not sampled and returned in 2.9 seconds.

Fix: `online.background` runs the turn judge, the edit judge, and the edit-pair upload on a daemon thread after the response. A failure is logged and never raised. Tests replace it with an inline runner. `test_an_online_check_runs_off_the_turn_and_a_failure_is_only_logged` covers the thread. A daemon thread is lost if the process exits mid-check, which is acceptable for a sampled online score.

## 2026-10-07 — A paused turn showed the previous turn's reply

Status: bug

What broke: On a case with an earlier answer, a later proposal (cancel, refund) was saved with the earlier answer's text, although its decision and citations were right. The case thread keeps the last turn's state in Postgres. A turn that pauses for approval stops before `compile_followup` writes `followup`, so `run_turn` read the stale `followup` from the checkpoint. Slice 1 had the same bug for a refund asked after another question. The tests never ran a second turn that pauses, and the walkthrough checked only the status.

Evidence: In the browser dry run, "How long does a customer have to return a pair of shoes?" followed by "Please cancel order NS-1004." showed the shoes answer cited as ORD-CANCEL.

Debug steps: `test_a_proposal_after_an_answer_shows_its_own_text` in `apps/api/tests/test_checkpointer.py` fails on the old code ("Thirty days." instead of the refund text) and passes now.

Fix: Each turn's input clears `followup`, and a paused turn falls back to its own `text`. `packages/agent/northstar/graph.py`.

## 2026-10-07 — A customer's stated preferences carry across cases (issue #77)

Status: decision

What changed: When a bound case's message states a contact channel ("I prefer email", "contact me by text"), the channel goes into LangGraph's `PostgresStore` under `("customers", customer_id, "prefs")`, key `contact_channel`, with the date it was stated. Only the derived channel (email, phone, or text) is stored, never the customer's free text, so a payment number, credential, or secret cannot become a preference. The case view returns the customer's preferences with the history record, the history panel shows them, and an unbound case reads none. A preference never changes an amount, a citation, or a handbook answer.

Evidence: R20 in `prd.md`. `AGENTS.md` (Customer history) names that namespace. [Stores](https://docs.langchain.com/oss/python/langgraph/stores).

Debug steps: `apps/api/tests/test_preferences.py`. The first run failed with "the connection is closed" on 60 tests. `PostgresStore.from_conn_string` returns a generator-backed context manager, and the entered store was kept while the context was dropped. The context was garbage-collected and closed the connection. The context is now kept alongside the store, as `memory.graph_for` does for the saver.

Fix: `packages/agent/northstar/preferences.py`, `cases.py`, the desk page.

## 2026-10-07 — A specialist's edit is kept beside the original (issue #67)

Status: decision

What changed: A proposal keeps its proposed amount in its own column, so a lead's amount edit no longer overwrites it. The case shows both amounts. The agent's draft and the specialist's final text were already saved together (R31). Each edit pair (draft and final text, or proposed and edited amount) is sent to LangSmith on the turn's root run. It goes as `specialist_edit` feedback with a `correction` (`{"followup": after}`) and a before/after comment, and the run is added to the `Northstar specialist edits` annotation queue. A pair becomes a labeled case only when a person adds it under a new dataset version. It never changes the handbook. The edited run still gets the groundedness judge. A LangSmith outage logs a warning and does not undo the close or the ticket.

Evidence: R18 in `prd.md`. [Annotation queues](https://docs.langchain.com/langsmith/annotation-queues). The installed client has `create_annotation_queue`, `list_annotation_queues`, `add_runs_to_annotation_queue`, and `create_feedback(correction=...)`.

Debug steps: `apps/api/tests/test_edit_judge.py` checks the pair sent for a draft edit and an amount edit, and that an unchanged draft sends nothing. Checked live: the queue was created, the run is in it, and the feedback carries the correction. A process that loads the ONNX reranker on macOS can print a `libc++abi ... recursive_mutex` abort at interpreter exit, after all work is done. pytest's exit code stays 0.

Fix: `packages/agent/northstar/online.py`, `cases.py`, the desk page.

## 2026-10-07 — A lead sees the handbook gaps list (issue #76)

Status: decision

What changed: An abstain now keeps the top reranked sections that fell under `RETRIEVAL_SCORE_TAU`, with their scores. They travel through the graph state and are saved on the message. `GET /gaps` (lead only) groups handbook abstains by question, ignoring case, spacing, and trailing punctuation. Each group shows how often it happened, when it last happened, and the best score per retrieved section. Groups are ordered by frequency, then by most recent. Catalog abstains are not handbook gaps and are left out. The questions are the screened text already saved on the case, so no customer personal data appears. The list is read-only and changes no handbook section. Slice 1 has no policy owner login, so the lead sees the list on the case desk.

Evidence: R19 in `prd.md`.

Debug steps: `apps/api/tests/test_gaps.py` sets the threshold above 1, so a covered question abstains with its weak sections. A threshold of 0.999 was not enough, because FlashRank scores the gold section above it. The local Playwright screens spec passes with the new section.

Fix: `packages/agent/northstar/retrieve.py`, `handbook.py`, `graph.py`, `cases.py`, `apps/api/northstar_api/main.py`, the desk page.

## 2026-10-07 — An escalation hands off a packet that stands alone (issue #73)

Status: decision

What changed: Every escalated case carries a handoff packet with these lines: Asked, Handbook, Missing, Order, Sections read, Tried (the agent's earlier decisions on the case, with their citations), and Owner. The owner is legal for chargebacks, lawyers, and regulators (ESC-LEGAL), policy for a source that conflicts with the handbook (ESC-WHEN), and support lead for an exception, suspected fraud (ESC-FRAUD), or an escalation a specialist makes by hand. A hand escalation's packet carries the specialist's note as what is missing. The question and the note are run through the same personal-data screen as the draft. The packet is stored on the case and shown on the Escalated case desk.

Evidence: ESC-WHEN asks the handoff to name the question, the order id, the sections read, and what is missing. ESC-FRAUD and ESC-LEGAL in `data/policy/support-escalation.md`. R17 in `prd.md`.

Debug steps: `apps/api/tests/test_handoff.py`, plus policy-conflict and fraud rows in `SLICE2_CASES`. The slice 1 escalation tests still pass, because the Asked, Handbook, and Missing lines are unchanged.

Fix: `packages/agent/northstar/escalate.py`, `cases.py`, the desk page.

## 2026-10-07 — The card screen masked digits inside a ticket id

Status: bug

What broke: A duplicate draft that named a ticket id sometimes showed it mangled, for example `b4ae3b*********0888e-...`. The card pattern in `privacy.screen` matched a run of 13 or more digits and dashes inside a UUID (`77-5903-4050-888`), because it only refused a neighbouring digit, not a neighbouring letter. The failure came and went with the random digits in the id.

Evidence: `test_a_completed_cancel_blocks_a_second_cancel_but_not_another_action` failed once locally with that masked id.

Debug steps: Read the saved draft. Matched the card pattern by hand against the id.

Fix: The card pattern refuses a neighbouring letter or digit on both sides. Spaced and dashed card numbers are still masked. `test_an_id_with_digit_runs_is_not_mistaken_for_a_card` uses the id that failed.

## 2026-10-07 — A lead decides from the approval queue (issue #72)

Status: decision

What changed: Each waiting-list row now carries the customer's ask, the draft, the action, the amount when there is one, the details, the citations, and an order summary (lines, status, total). The row also has approve, edit, and reject. A row links to a read-only case desk for that case (`GET /cases/{case_id}`, lead only), which hides the specialist's bind, ask, and close controls. The slice 1 list never linked to the case. The accessibility walkthrough now opens a case from the queue and returns, with an axe scan on that view.

Evidence: R16 in `prd.md`.

Debug steps: `apps/api/tests/test_approval_queue.py`. A local run of `apps/web/tests/screens.spec.ts` passes.

Fix: `packages/agent/northstar/cases.py`, `apps/api/northstar_api/main.py`, the desk page, the screens spec.

## 2026-10-07 — A second proposal for the same order and action is blocked (issue #71)

Status: decision

What changed: Each proposal decision belongs to an action family (refund, cancel, address change, exchange, warranty claim). The family map in `northstar.actions` is also the source of `PROPOSALS`. After a rule proposes, the case store looks for a ticket on the same order and family, or a proposal for them waiting on another case. When one exists, the draft is `duplicate`: it names that ticket or case and makes no proposal. A different family on the same order is still proposed. The refund rule now treats only refund or cancel tickets as already paid. Before this, an exchange or address ticket made a later refund say "already refunded".

Evidence: R15 in `prd.md`. A slice 1 test expected a deny proposal for a second refund after a ticket. It now expects the duplicate reply that names the ticket, which still meets R6. The `refunds` field case (NS-1003) still proposes a deny citing REF-DENY.

Debug steps: `apps/api/tests/test_duplicates.py`.

Fix: `packages/agent/northstar/actions.py`, `cases.py`.

## 2026-10-07 — Give the next step for a lost or delayed shipment (issue #75)

Status: decision

What changed: A report of a late or missing package is a gated action. The next step follows the order record:
- **Delivered, under 48 hours:** wait and check the door (SHIP-DNR).
- **Delivered, after 48 hours:** escalate to a person, with no refund (SHIP-DNR, ESC-WHEN).
- **Placed or packed:** not shipped yet (SHIP-SLA).
- **Shipped, inside 7 business days of the ship date:** not late (SHIP-SLA).
- **Shipped, inside the next 2 business days:** past the window, not yet delayed (SHIP-SLA, SHIP-DELAY).
- **Shipped, after that and before day 14:** delayed, so wait, with no refund (SHIP-DELAY, SHIP-LOST).
- **Shipped, on day 14 or later:** lost. A refund proposal for the order total, with no return (SHIP-LOST).

No carrier, tracking number, or scan is stated. The handbook's lost-package remedy is a refund, so no replacement is proposed for a lost package. REP-REPLACEMENT covers damaged or defective items only. Business days skip Saturday and Sunday.

Evidence: SHIP-SLA, SHIP-DELAY, SHIP-LOST, and SHIP-DNR in `data/policy/shipping-and-delivery.md`.

Debug steps: `apps/api/tests/test_shipment.py` tests each window on the pure rule with fixed dates. With a Tuesday ship date, the delayed stretch has no days, because 9 business days already reaches day 14. The labeled rows (lost, inside the window, delivered but not received, not shipped) do not depend on the date.

Fix: `packages/agent/northstar/actions.py`, `cases.py`, `evals/labeled.py`.

## 2026-10-07 — Draft a warranty claim behind the approval gate (issue #74)

Status: decision

What changed: A warranty or defect report is a gated action with no amount. The return window applies first, so a defect inside the window takes the refund path. Coverage starts the day after the window ends and runs 90 days for apparel and footwear and 1 year for everything else. A covered defect becomes a `warranty_claim` proposal citing WAR-COVERAGE and WAR-CLAIM, with the coverage end date and the customer's description for the lead. The draft says a person submits the claim and never says it is approved. Wear, cuts, stains, misuse, damage after delivery, a change of mind, and final-sale lines get WAR-EXCLUSIONS. Ended coverage gets WAR-COVERAGE. A report with no defect described asks for one. The seed adds a desk speaker past its return window and a linen shirt past its coverage.

Evidence: `data/policy/warranty.md`.

Debug steps: `apps/api/tests/test_warranty.py`, plus five rows in `SLICE2_CASES`.

Fix: `packages/agent/northstar/actions.py`, `cases.py`, `evals/labeled.py`.

## 2026-10-07 — Propose an exchange instead of a refund (issue #70)

Status: decision

What changed: An exchange or swap request is a gated action with no amount. It is proposed only when every check passes:
- the line is apparel and footwear or bags and accessories, delivered, inside the return window, and not worn;
- it has not been exchanged before;
- the wanted size is on the catalog row, and the row says in stock.

The proposal cites EXC-ELIGIBILITY and EXC-PROCESS and carries "item: size X to size Y" for the lead. Each failed check gets a cited answer: EXC-ELIGIBILITY, EXC-DIFFERENT-ITEM, EXC-LIMIT, EXC-STOCK, or REF-CATEGORY. A request with no size asks for one. The catalog row has one in-stock flag per item, not one per size, so stock is read at item level. A rain jacket that is not in stock was added to the seed catalog, with an order for it.

Evidence: `data/policy/exchanges.md`.

Debug steps: `apps/api/tests/test_exchange.py` (an approved exchange, then EXC-LIMIT on the same line), plus five rows in `SLICE2_CASES`.

Fix: `packages/agent/northstar/actions.py`, `cases.py`, `evals/labeled.py`.

## 2026-10-07 — Change the ship-to address before shipment (issue #69)

Status: decision

What changed: An address request is a gated action with no amount. A placed or packed order becomes an `address_change` proposal citing SHIP-ADDRESS. The new address (the text after the last "to" that holds a street number) goes on the proposal details for the lead, and the customer-facing draft leaves it out. A shipped or delivered order gets a cited answer. A request with no new address asks for it. An amount edit on this proposal is refused with 422.

Evidence: SHIP-ADDRESS in `data/policy/shipping-and-delivery.md` allows placed or packed. ORD-MODIFY covers quantity and size changes, not the address.

Debug steps: `apps/api/tests/test_address_change.py`, plus five rows in `SLICE2_CASES`.

Fix: `packages/agent/northstar/actions.py`, `evals/labeled.py`.

## 2026-10-07 — Cancel an unshipped order (issue #68)

Status: decision

What changed: A cancel request is a gated action. Only a placed order becomes a cancel proposal, for the full order total including shipping, citing ORD-CANCEL. A packed, shipped, or delivered order gets a cited answer and no proposal. Seed orders now carry handbook statuses (placed, packed) and a ship date. A refund request on an order that has not been delivered is answered with ORD-CANCEL instead of a refund proposal, because the return window counts from delivery. Before this, the refund rule failed on an empty delivery date. A policy question with no order id ("Can an order be cancelled after it ships?") goes to the handbook, not to the gated path. Slice 2 labeled desk cases live in `SLICE2_CASES`, a new dataset version beside the frozen 40.

Evidence: ORD-CANCEL in `data/policy/order-changes.md`.

Debug steps: `apps/api/tests/test_cancel.py` and `apps/api/tests/test_slice2_cases.py`.

Fix: `packages/agent/northstar/actions.py`, `cases.py`, `evals/labeled.py`.

## 2026-10-07 — A gated proposal carries any action (issue #66)

Status: decision

What changed: Gated actions live in one table in `northstar.actions`: the request pattern, the handbook rule, and the missing-order text. The router, the pause in `compile_followup`, the citation guard, the online safety code, and the release bar all read the decision set `PROPOSALS` from there. The refund rule moved there unchanged. A proposal now records an id and free-text details. A ticket records its proposal, action, and order, and it is unique per proposal instead of per case, so a second proposal on the same case gets its own ticket. A proposal with no amount refuses an amount edit with 422.

Evidence: Before the change, approving a second proposal on a case returned the first ticket, because the ticket was found by case id. The decision set was copied in four places.

Debug steps: The 75 existing tests pass with no change in refund, partial credit, or deny behavior. `apps/api/tests/test_gated_actions.py` covers the table, a second ticket on the same case, and the waiting list fields.

Fix: `packages/agent/northstar/actions.py`, `cases.py`, `graph.py`, `handbook.py`, `online.py`, `evals/release_bar.py`, the desk page. The attached LangSmith safety evaluator keeps the code it was created with. Re-create it when new proposal decisions should be checked online.

## 2026-10-07 — Built-in middleware on the create_agent subgraphs, and masked traces

Status: decision

What changed: Each `create_agent` subgraph now runs behind built-in middleware:
- `PIIMiddleware`: secrets blocked, email redacted, card masked, phone redacted, on input, model output, and tool results. Phone and secrets use detectors built from the same patterns as `privacy.screen`.
- `ModelCallLimitMiddleware`: 3 calls per run, then end.
- `ToolCallLimitMiddleware`: the desk runs once per run.
- `ModelRetryMiddleware`, and `ModelFallbackMiddleware` only when `AGENT_FALLBACK_MODEL` is set.
- `ToolErrorMiddleware` outside `ToolRetryMiddleware` (`on_failure="error"`), so a desk failure returns a `lookup_failed` draft that fills in no facts.

A secret block returns the fixed secret reply. A model failure still falls back to the desk without a model. `HumanInTheLoopMiddleware` and `SummarizationMiddleware` are not attached. The subgraph has no ticket tool, because the lead's API decision after the `compile_followup` interrupt writes the ticket. The subgraph sees one message per turn. `AGENTS.md` now says so under the middleware table.

A live turn also showed that the raw question reached LangSmith on the LangGraph root, the router, the node runs, and the PII middleware's own runs. Only the model calls were masked. `run_turn` now traces through a client whose anonymizer applies `privacy.screen` to every input and output.

Evidence: [Built-in middleware](https://docs.langchain.com/oss/python/langchain/middleware/built-in). `ToolErrorMiddleware`'s docstring in langchain 1.4.3 says to compose it with `ToolRetryMiddleware` placed inner with `on_failure="error"`. [Mask inputs and outputs](https://docs.langchain.com/langsmith/mask-inputs-outputs). `langsmith.anonymizer.create_anonymizer` takes a `(text, path) -> text` replacer.

Debug steps: `apps/api/tests/test_middleware.py` drives the real `create_agent` with a scripted chat model. It checks that the model never sees email, phone, or a full card, that the desk runs once when the model asks twice, that a failing desk is retried once and then returns `lookup_failed`, and that a secret stops the turn before any model call. All four fail when the middleware list is empty. Live Gemini turn on `northstar-local`: all middleware runs appear in the trace, one desk call, and the email, phone, and card appear in none of the 37 runs.

Fix: `packages/agent/northstar/graph.py`, `packages/agent/northstar/privacy.py`, `packages/agent/northstar/agent_model.py`, `.env.example`. A desk retry runs the desk again, so a transient failure after the token charge charges the daily budget twice.

## 2026-10-07 — Branch protection on uat, dev, prod, and main

Status: decision

What changed: `uat`, `dev`, `prod`, and `main` now require a pull request and the CI checks `Test API` and `Lint and build console` before a merge. Admins are included. Force pushes and branch deletion are off. Zero approving reviews are required, because the owner is the only contributor. This meets the #22 criterion "a miss blocks promotion to uat": the release bar and the axe scan are those two checks.

Evidence: The branches had no protection and the repo had no rulesets. Before this change, a failing CI only skipped the Deploy job and did not block the merge. AGENTS.md (Branching and promotion) asks for protection on all four. Set through `PUT /repos/{owner}/{repo}/branches/{branch}/protection` ([branch protection API](https://docs.github.com/rest/branches/branch-protection#update-branch-protection)).

Debug steps: Read the protection back for each branch: required checks, admin enforcement, a PR required, no force pushes.

Fix: GitHub repository settings. Emergency bypass means turning admin enforcement off for that branch, on purpose.

## 2026-10-07 — The live judge scored a model call instead of the LangGraph root

Status: bug

What broke: `run_turn` took the run id from `collect_runs().traced_runs[0]`. With a live Gemini key, that was the first `ChatGoogleGenerativeAI` child run, not the LangGraph root. So `policy_groundedness` landed on a model call, and an edit judged later would land on the same wrong run. After the first fix, passing `project_id` to `create_feedback` raised "project_id cannot be provided if run_id or trace_id is provided". The judge's `except Exception: pass` hid that error, so the turn looked fine and no score was written.

Evidence: One live abstain turn on `northstar-local`. The judged id had name `ChatGoogleGenerativeAI` and its trace id was the LangGraph root's id. The safety rule had scored the real root (`safety = 1`), so the run rule was fine. Only the judge's run id was wrong. The installed SDK (langsmith 0.14.4) also warns that run-level feedback without `session_id` is deprecated ([feedback create migration](https://docs.langchain.com/langsmith/smithdb-sdk-migration-feedback#feedback-create)).

Debug steps: Listed every run in the trace with its parent and trace ids. Read `RunnableConfig.run_id` in langchain-core ("Unique identifier for the tracer run for this call"). Called `record_judge` directly to surface the swallowed error.

Fix: `run_turn` creates a `uuid7` and passes it as `config["run_id"]`, so the root run id is known before the graph runs. `_post_feedback` passes the project id as `session_id`. Judge failures now log a warning instead of passing silently. Checked live: the judged run is the `LangGraph` root with `decision = abstain`, and it carries `policy_groundedness = 1`. pytest turns tracing off, so this path is checked live, not in CI.

## 2026-10-07 — Every edit and every handoff escalation is judged

Status: decision

What changed: The judge sample now covers every run a person edited, as AGENTS.md asks ("a 10% random sample plus every run that abstained, escalated, or was edited by a specialist"). A live turn stores its LangGraph root run id on the assistant row in `case_messages.run_id`. When the specialist resolves or escalates with final text that differs from the draft, or a lead edits the proposed amount, the API posts `policy_groundedness` feedback to that same run with `edited=True`. The judge reads the specialist's final text, or the draft plus the lead's new amount. A legal or exception handoff used to return before the graph ran, so it had no LangGraph trace and neither the safety rule nor the judge saw it. It now goes through `run_turn` with the handoff as the fixed desk draft, so it has a root run with `decision = escalate`. The sampling rule lives only in `northstar.online.should_judge`. `evals.release_bar.online_checks` imports it instead of keeping a copy.

Evidence: Before the change, `online._should_judge` took only the decision and the sample, and `release_bar.online_checks` already took `edited`. The rule existed in two places and they disagreed. `CaseStore.ask` called `handoff()` before `run_turn`, so the checkpointer had no state for an escalated case thread. [Online evaluators](https://docs.langchain.com/langsmith/online-evaluations-llm-as-judge).

Debug steps: `apps/api/tests/test_edit_judge.py` drives the API with a fake grader and a fake feedback writer. It checks that an edited draft is judged on its turn's run id, that an unchanged draft is not, that a lead's amount edit is judged, and that a chargeback handoff leaves `decision = escalate` in the graph checkpoint. No OpenRouter call runs in CI.

Fix: `packages/agent/northstar/online.py`, `packages/agent/northstar/cases.py`, `packages/agent/northstar/graph.py`, `evals/release_bar.py`. With a live model key, a handoff now costs one `create_agent` call, the same as any other routed turn. The desk still returns the fixed handoff text. A run can get two `policy_groundedness` scores: one from the sample at turn time and one after the edit.

## 2026-10-07 — Safety scores every LangGraph trace, and a judge scores a sample

Status: decision

What changed: A code evaluator named northstar-safety is attached to the local tracing project on every root run named LangGraph, at sampling rate 1. The filter is `eq(name, "LangGraph")`. A live turn also asks the OpenRouter judge for groundedness when the decision is abstain or escalate, or when a random sample is below 0.1, and writes `policy_groundedness` feedback. A specialist edit is not a field on the trace, so that case is not selected.

Evidence: [Trace query syntax](https://docs.langchain.com/langsmith/trace-query-syntax) and `POST /api/v1/runs/rules` in the platform OpenAPI. The installed `client.evaluators.list` returns an async paginator, so the attach call uses the sync HTTP client. Backend version reported by the API was 0.18.5.

Debug steps: Listed root runs. LangGraph outputs include `decision` and `citations`. RunnableSequence runs are the pairwise judge and are outside the filter.

Fix: `packages/agent/northstar/online.py`.

## 2026-10-07 — Every saved draft is checked against the section registry

Status: decision

What changed: Before a draft is saved, and before a refund proposal is written, a citation that is not in `SECTION_IDS.md` or a policy decision with no citation becomes an abstain. The proposal row is not written in that case. The LangSmith SDK in this repo can create an evaluator, and it has no run-rule create method. A rule was not attached with a guessed payload. `openevals` is not installed, so a live groundedness judge was not added.

Evidence: Issue #22 asks for safety code on every run. [Online evaluators](https://docs.langchain.com/langsmith/online-evaluations-llm-as-judge) attach through a run rule. The installed client exposes `evaluators.create` and no run-rule resource.

Debug steps: None.

Fix: `packages/agent/northstar/handbook.py` `guard_draft`. Attach the judge when the SDK can create the rule.

## 2026-10-07 — Dev cannot read another environment's handbook

Status: decision

What changed: Pinecone search and ingest take the namespace from `NORTHSTAR_ENV`. `local` and `dev` may only use `handbook-dev`. `uat` may only use `handbook-uat`. `prod` may only use `handbook-prod`. A mismatch raises before any query. The console's server calls stay on `FASTAPI_URL` or a same-origin path. No deploy hook was added.

Evidence: [AGENTS.md environments](AGENTS.md) already names one namespace per environment. Issue #5 says a test in dev must not touch another environment's data.

Debug steps: None.

Fix: `packages/agent/northstar/retrieve.py`.

## 2026-10-07 — Tool names come from the tools task this install emits

Status: decision

What changed: `task_names` appends each tool name after a task named `tools`. The parent debug stream already includes that task when `create_agent` is invoked inside the node. The agent is not passed to `add_node`, because its state is `messages` and the parent state is not.

Evidence: [Subgraphs](https://docs.langchain.com/oss/python/langgraph/use-subgraphs) say different state schemas are invoked inside a node. [Evaluate a complex agent](https://docs.langchain.com/langsmith/evaluate-complex-agent) reads `payload["input"]["messages"][-1].tool_calls`. A nested agent on this install emits `payload["input"]` as the tool-call list, and the parent stream shows `model`, then `tools`.

Debug steps: Streamed a nested `create_agent` with `stream_mode="debug"` and `subgraphs=True`. Indexing `input["messages"]` raised `TypeError` because `input` was a list.

Fix: `packages/agent/northstar/graph.py` reads both shapes.

## 2026-10-07 — A live turn asks create_agent, and the desk still decides

Status: decision

What changed: When `GOOGLE_API_KEY` is set and pytest is not running, the refund and support nodes call `create_agent` with the existing desk function as the only tool. The tool ignores the model's question and uses the routed one. If the agent errors or skips the tool, the node calls the desk function itself. Pytest stays on that direct call.

Evidence: [Agents](https://docs.langchain.com/oss/python/langchain/agents). `create_agent` returns a compiled graph. It is invoked inside the node, not mounted as a subgraph, so the trajectory names stay the same.

Debug steps: None.

Fix: `packages/agent/northstar/graph.py`. Mount the agent as a subgraph when the trajectory must list the inner tool call. Middleware stays off until a limit or a PII pass is the bug.

## 2026-10-07 — The pairwise judge prefers v1 on the four desk rows

Status: decision

What changed: The held-out replies were compared by the quiz judge's model, with the order randomized. Identical handbook replies were a tie and were not sent. The judge preferred v1 on exception, proposer-cannot-approve, catalog-material, and out-of-window. It preferred v0 on none.

Evidence: [Pairwise evaluation](https://docs.langchain.com/langsmith/evaluate-pairwise). `evaluate_comparative` needs two existing experiment names. Those experiments are not uploaded, so this run is the same judge locally.

Debug steps: None. The picks are in `results/v0_v1.md`.

Fix: `evals/pairwise.py`. Upload the two experiments before calling `evaluate_comparative`.

## 2026-10-07 — A proposal pauses the graph thread

Status: decision

What changed: A refund, partial credit, or denial pauses in `compile_followup` with `interrupt` when the thread has a checkpointer. Approve, edit, and reject resume that thread. The case row still inserts the ticket. Turns with no checkpointer, including the path scorer, do not pause.

Evidence: [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts). The node restarts on resume, so the pause is after the proposal is already in state. Putting it in the refund node would propose twice.

Debug steps: A refund turn on one connection left `compile_followup` pending. A second connection read that interrupt. Resume wrote `followup`.

Fix: `packages/agent/northstar/graph.py`. `create_agent` subgraphs stay plain nodes until the model has to choose tools.

## 2026-10-07 — Handbook candidates come from Pinecone when the key is set

Status: decision

What changed: Outside pytest, `retrieved_answer` asks Pinecone for 20 sections, then FlashRank keeps 4. The index is `northstar-handbook` in us-east-1, dimension 1536, namespace `handbook-dev`. Embeddings are `gemini-embedding-001`, normalized because that model must be normalized below 3072 dimensions. Pytest keeps the overlap pick.

Evidence: [Pinecone integration](https://docs.langchain.com/oss/python/integrations/vectorstores/pinecone) and [Gemini embeddings](https://ai.google.dev/gemini-api/docs/embeddings). Starter indexes are us-east-1 only.

Debug steps: Ingested the handbook sections and queried an apparel question. The top reranked id was recorded in the run, not in this file.

Fix: The Pinecone key stays in `.env`.

## 2026-10-07 — Tracing turns on from the local environment

Status: decision

What changed: A turn outside pytest loads `.env` and, when `LANGSMITH_TRACING=true`, also sets `LANGCHAIN_TRACING_V2`. The project name is `northstar-local`. Pytest does not load that file.

Evidence: The langsmith-trace skill says a LangGraph app is traced by those environment variables. [Checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers) are unchanged.

Debug steps: A graph turn was sent and listed in the `northstar-local` project.

Fix: Keys stay in `.env`. They are not committed.

## 2026-10-07 — The quiz judge agrees with the handbook labels

Status: decision

What changed: The quiz judge scored the five handbook rows in `train_judge`. It agreed with the human label on all five. `results/judge_calibration.md` says `agreement: 5/5` and `test split: open`. Desk rows in that split stay on code checks.

Evidence: Each student text was the handbook answerer. Each ground truth was the gold section rule, or the abstain text. One call returned an empty provider response and was retried. The recorded scores are from the successful calls.

Debug steps: Compared `is_correct` to `matches` for apparel-window, fourteen-day-trap, ship-regions, support-hours, and favorite-color.

Fix: The test split stays closed unless that file says `test split: open`.

## 2026-10-07 — The walkthrough image is the turn chart

Status: decision

What changed: `diagrams/northstar-architecture.png` and a JPEG copy are rendered from the one-turn chart in `architecture.md`. There is no separate canvas file.

Evidence: `AGENTS.md` says the walkthrough shows that image, and the chart is the layout.

Debug steps: Opened the PNG. It shows the filter, the router, both agents, and the safe reply.

Fix: Re-render that file when the boxes in the chart change.

## 2026-10-07 — The graph thread is stored in Postgres

Status: decision

What changed: Each case turn is checkpointed with `PostgresSaver` on that case id. A second connection can read the same `followup`. The case row is still the approval record.

Evidence: [Checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers) say `PostgresSaver.from_conn_string` keeps the thread, and `setup()` creates the tables. `InMemorySaver` dies with the process.

Debug steps: A refund turn was written on one connection and read back on another.

Fix: One open connection per database URL for the process.

## 2026-10-07 — The agent model is Gemini 3 Flash

Status: decision

What changed: Handbook replies on the server are phrased by `gemini-3-flash-preview`. The key is `GOOGLE_API_KEY`. Citations still come from the retrieved sections. During pytest the retrieved draft is kept. The judge stays on OpenRouter.

Evidence: [ChatGoogleGenerativeAI](https://docs.langchain.com/oss/python/integrations/chat/google_generative_ai) reads `GOOGLE_API_KEY`. The model id is `gemini-3-flash-preview` ([model card](https://ai.google.dev/gemini-api/docs/models/gemini-3-flash-preview)).

Debug steps: None yet.

Fix: The key stays in the local `.env`, which git ignores.

## 2026-10-07 — The judge is Nemotron on OpenRouter

Status: decision

What changed: The quiz judge calls `nvidia/nemotron-3-ultra-550b-a55b:free` through OpenRouter. The key is `OPENROUTER_API_KEY`. The agent model stays a different setting. No score is written when the key is missing, and the calibration file is unchanged.

Evidence: [OpenRouter quickstart](https://openrouter.ai/docs/quickstart) uses an OpenAI-compatible chat completions endpoint. [LLM-as-a-judge](https://www.langchain.com/resources/llm-as-a-judge) says to use a different model for judging than for generation. The model id contains `:free`, so the provider is passed separately and that colon is not treated as a model prefix.

Debug steps: None yet. A missing key still returns no score.

Fix: The key stays in the local `.env`, which git ignores. It is not committed.

## 2026-10-07 — Trajectory score is the published subsequence

Status: decision

What changed: `evals/trajectory.py` is `trajectory_subsequence` as published. `extra_step_count` is the actual steps the walk did not match. A refund path that also calls `create_refund_ticket` still scores 1.0 and counts that call as one extra step.

Evidence: [Evaluate a complex agent](https://docs.langchain.com/langsmith/evaluate-complex-agent). The function returns `False` when the reference is longer than the actual path. Otherwise it returns the fraction of expected steps found in order.

Debug steps: A debug stream of a refund question produced `intent_classifier`, `refund_agent`, `compile_followup`.

Fix: None. Do not require a perfect 1.0 on a compound question.

## 2026-10-07 — The quiz judge does not score without a model key

Status: decision

What changed: `evals/judge.py` is the teacher-quiz grader from the complex-agent guide. `final_answer_correct` returns no score when `OPENAI_API_KEY` is unset. `score_examples` skips the test split while `results/judge_calibration.md` still says the judges have not been run. Nothing writes an agreement number.

Evidence: [Evaluate a complex agent](https://docs.langchain.com/langsmith/evaluate-complex-agent) grades only factual accuracy against the ground truth, rejects conflicting statements, and allows extra detail that stays accurate. Structured output is `reasoning` plus `is_correct`. Temperature is 0. The judge model is `JUDGE_MODEL`, default `gpt-4o-mini`. No key is configured in this environment.

Debug steps: None. The calibration file is compared before and after the check.

Fix: Call the model only after a key exists. Record agreement in `results/judge_calibration.md` from that run, then allow the test split.

## 2026-10-06 — Handbook rerank is FlashRank on a local top 20

Status: decision

What changed: A handbook turn on the desk calls `retrieved_answer`. Overlap still picks 20 sections. `flashrank.Ranker` with `ms-marco-MiniLM-L-12-v2` keeps at most 4 whose score is at least `RETRIEVAL_SCORE_TAU` (0.2). `answer()` is unchanged and remains the function the v0 scorer calls by default. The new function is passed into `score` and `score_handbook`.

Evidence: On train_judge and dev, the weakest gold score was 0.41 (`FAQ-HOURS`) and the abstain scored 0. The 14-day trap's next section scored 0.15, and that section must stay out so the draft does not repeat "14 days". 0.2 sits in that gap. Pinecone was not called: `PINECONE_API_KEY` is unset. Loading the ranker raised this process from 60 MB to 157 MB max RSS on this Mac. That fits under the 512 MB Render instance. It was not measured on Render. The deploy hook is unset, so there is no running host to sample.

Debug steps: Scored train_judge and dev at 0.5, 0.2, and 0.05. At 0.5, `support-hours` abstained. At 0.05, the 14-day trap kept a weak section. 0.2 passed both splits. The held-out handbook rows were checked after the threshold was chosen.

Fix: `packages/agent/northstar/retrieve.py`. Swap the overlap pick for Pinecone top-20 when the index exists. Do not retune the threshold on the test split.

## 2026-10-06 — The router is a StateGraph in front of the desk

Status: decision

What changed: A turn that passes the input checks now runs a LangGraph `StateGraph`. `intent_classifier` returns `Command(goto=...)` to `refund_agent` or `support_agent`. Both write `followup` in `compile_followup`. The nodes call the refund and support functions the desk already had. They are not `create_agent` subgraphs.

Evidence: [Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api) says a node may return `Command(goto=...)`, and that static edges from that same node would also run, so the classifier has no static edge. [Evaluate a complex agent](https://docs.langchain.com/langsmith/evaluate-complex-agent) reads `result["followup"]` and checks `command.goto` on the classifier node alone. No `OPENAI_API_KEY` is configured, so a model subgraph would not be a real call.

Debug steps: None. The desk tests stay the check that refund, order, catalog, and handbook replies did not change.

Fix: `packages/agent/northstar/graph.py` is the router. `PostgresSaver` and `create_agent` wait until a model key and a checkpointer are real. Do not mark the phase plan done on this step.

## 2026-10-06 — Modularity is a core requirement

Status: decision

What changed: Readability, maintainability, and modularity are required in `AGENTS.md`. A feature change stays in that feature's module. A new retrieval engine, model, or database is an adapter behind an interface.

Evidence: Malatesha, 2026-10-06. Later changes must not rewrite unrelated code.

Debug steps: The ports-and-adapters layout was already in the code-structure section. It was easy to miss, and case logic was accumulating in one module.

Fix: State the rule next to the build gate. New features, starting with the v0 handbook eval, get their own module and call the existing answer function.

## 2026-10-06 — Handbook v2, written in full

Status: decision

What changed: Handbook v1 is replaced by `northstar-policy-v2`. New sections cover the company, category windows, exchanges, payments, promotions, gift cards, and store credit. Ids that already existed are kept. The registry lists every id.

Evidence: Topics and number ranges follow published retail practice. The sentences are original. Source pages that were not copied:

- https://www.amazon.com/gp/help/customer/display.html?nodeId=GKM69DUUYKQWKWX7
- https://www.amazon.com/gp/help/customer/display.html?nodeId=GKQNFKFK5CF3C54B
- https://www.amazon.com/gp/help/customer/display.html?nodeId=201077750
- https://zoutons.com/news/flipkart-return-replacement-policy-2026
- https://www.target.com/help/articles/returns-exchanges/returns
- https://www.target.com/help/articles/policies-guidelines/price-match-guarantee
- https://www.zappos.com/c/shipping-and-returns
- https://www.evga.com/legal/store/

Kept v1 ids: REF-WINDOW, REF-ELIGIBILITY, REF-PARTIAL, REF-DENY, REF-DAMAGED, REF-FINAL-SALE, SHIP-SLA, SHIP-DELAY, SHIP-LOST, SHIP-ADDRESS, WAR-COVERAGE, WAR-EXCLUSIONS, WAR-CLAIM, ORD-CANCEL, ORD-MODIFY, ORD-TRACK, ESC-WHEN, ESC-ABUSE, ESC-LEGAL, PII-MINIMIZE, PII-SHARE, FAQ-HOURS, FAQ-CONTACT, FAQ-ACCOUNT.

Conflict pass: the 14-day damage report is shorter than the 15-day electronics return window, and REF-DAMAGED says so. Exchange eligibility points at REF-CATEGORY instead of restating 30 or 15. Warranty begins the day after the return window ends. The numeral 14 also appears as days from the ship date (SHIP-LOST) and as days from delivery for a Northstar site price drop (PAY-PRICE-ADJUST). Those are different clocks, each defined in one section. The same is true of "3 to 5 business days" for a card refund (REF-TIMING) and for a pending authorization to drop off (PAY-DUPLICATE), and of the 2-business-day express span (SHIP-SLA) versus the extra wait after a delay (SHIP-DELAY).

Debug steps: Compared every heading in the handbook files with the registry. Every file id is in the registry.

Fix: Wrote the v2 handbook, replaced `SECTION_IDS.md`, and updated `AGENTS.md`, `CONTEXT.md`, and `explanation.md`.

## 2026-10-06 — Docs checked against current LangChain, LangGraph, and Pinecone pages

Status: decision

What changed:
- Rerank no longer imports `FlashrankRerank` from `langchain_community`. `langchain-community` was sunset on 2026-05-22. The `Reranker` adapter calls `flashrank.Ranker` with `model_name="ms-marco-MiniLM-L-12-v2"`. That model must be passed: the old wrapper defaults to `ms-marco-MultiBERT-L-12`.
- The in-memory checkpointer name in the contract is `InMemorySaver`, matching the current checkpointer docs. It is still not the production checkpointer.
- Phone is not a built-in `PIIMiddleware` type. Built-ins are `email`, `credit_card`, `ip`, `mac_address`, and `url`. Phone uses a custom detector. `HumanInTheLoopMiddleware` uses `interrupt_on` and `allowed_decisions` of `approve`, `edit`, and `reject`, and it requires a checkpointer. `ToolErrorMiddleware` requires `langchain>=1.3.14`.
- Pinecone Starter rerank quota is 500 requests per month per model for `bge-reranker-v2-m3`, and 60 per minute. That is the only rerank model on Starter. The earlier "500 per organization" wording was wrong. Starter indexes are AWS `us-east-1` only. The Pinecone notebook still creates a dense index at dimension 1536 with cosine distance.

Evidence:
- [Sunsetting langchain-community](https://github.com/langchain-ai/langchain-community/issues/674)
- [FlashRank models](https://github.com/PrithivirajDamodaran/FlashRank)
- [Built-in middleware](https://docs.langchain.com/oss/python/langchain/middleware/built-in)
- [Checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers)
- [Pinecone database limits](https://docs.pinecone.io/reference/api/database-limits)
- [Pinecone pricing](https://www.pinecone.io/pricing/)
- [Pinecone vector store](https://docs.langchain.com/oss/python/integrations/vectorstores/pinecone)
- [Evaluate a complex agent](https://docs.langchain.com/langsmith/evaluate-complex-agent) still publishes `trajectory_subsequence`, `client.aevaluate`, `compile_followup`, and `Command(goto=...)`. The Chinook refund path still mocks the write with `config={"env": "test"}`. Northstar still does not copy that.

Debug steps: Opened those pages on 2026-10-06. The old FlashrankRerank class URL returned 404 once and resolved later; the sunset issue is the reason to stop depending on the package.

Fix: Updated `AGENTS.md`, `architecture.md`, and `explanation.md`.

## 2026-10-06 — UX laws, accessibility, history panel, repo, spec

Status: decision

What changed:
- `prd.md` said the console is "one screen", while `AGENTS.md` listed four screens, including a customer history screen the PRD never specified. Both now say three screens: login, case desk, and the waiting for approval list.
- New P0 requirement R33: staff see a read-only history panel on the case desk (5 most recent cases).
- New P0 requirement R32: the console meets WCAG 2.2 AA.
- The PRD Experience section gained a visual hierarchy and a UX law table.
- The `AGENTS.md` Layout and Build order sections predated the phased plan. Both now point to `docs/plans/slice-1-build-phases.md`.
- Public GitHub repo created: https://github.com/PrasannaMalatesha/northstar-support-agent, with branches `main`, `dev`, `uat`, `prod`.
- Implementation spec written to `docs/spec.md` and published as a GitHub issue labeled `ready-for-agent`.

Evidence: [Laws of UX](https://lawsofux.com/), [What is new in WCAG 2.2](https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/), and Malatesha's choices (history panel, WCAG 2.2 AA, public repo, three test seams).

Fix: Updated `prd.md`, `AGENTS.md`, `architecture.md`, `explanation.md`, `CONTEXT.md`, and `docs/plans/slice-1-build-phases.md`.

## 2026-10-06 — PRD closed: contradictions removed, R28 to R31 added

Status: decision

What changed:
- A P0 "Waiting for approval" list lets leads find proposals. The P1 queue adds deciding from the list.
- P0 saves the draft and the final text. P1 adds review tooling.
- Preferences were removed from P0 history and arrive with P1 memory.
- P0 handbook answers cover every handbook topic.
- Unbound cases allow handbook and catalog questions only.
- Case status is Open, Waiting for approval, Resolved, or Escalated.
- The PRD handbook section now matches v2.
- Open points: none.

Evidence: A full read of `prd.md` found that P0 approval had no way for a lead to find proposals (the queue was P1), that step 7 saved edits while saving edits was P1, and that P0 history showed preferences that only P1 creates. Malatesha chose all resolutions, 2026-10-06.

Debug steps: None.

Fix: Updated `prd.md`, `AGENTS.md` (customer history), and `CONTEXT.md` (case status, unbound case). Rule added to the PRD: a feature not in the PRD is out of scope until it is added there first.

## 2026-10-06 — Real staff login replaces the shared demo secret; four-layer rate limiting

Status: decision

What changed: The shared password or API key is gone.
- FastAPI owns staff accounts (argon2id, seeded, no sign-up) and issues short-lived tokens. Auth.js `Credentials` keeps them in an encrypted httpOnly cookie, and only Next.js server route handlers call FastAPI.
- Rate limiting has four layers: login lockout in Postgres, slowapi request limits in memory, a daily token quota in Postgres, and model-call limiting in process.
- New PRD requirements R24 to R27.

Evidence:
- Auth.js recommends attaching the backend token on the server side in route handlers ([guide](https://authjs.dev/guides/integrating-third-party-backends)).
- slowapi with Redis blocks the event loop ([issue #130](https://github.com/laurentS/slowapi/issues/130)).
- Neon Auth tokens cannot carry custom claims ([docs](https://neon.com/docs/auth/guides/plugins/jwt)), so it was not chosen.
- Malatesha chose this, 2026-10-06.

Debug steps: None.

Fix: Updated `AGENTS.md` (Frontend, auth, and security; docs list), `prd.md` (staff login, fair use, R24 to R27, privacy, SSO note), and `architecture.md` (layer table).

## 2026-10-06 — create_agent subgraphs, customer history record, eval catalog, judge scaling

Status: decision

What changed:
- The support and refund subgraphs are now `create_agent` subgraphs under the LangGraph router, so built-in middleware applies.
- Structured output uses `ToolStrategy` with a Pydantic schema.
- Ticket creation has an idempotency key.
- Customer history is a short record built from app tables, never past transcripts.
- The eval catalog now names faithfulness, relevance, context recall and precision, hit rate, MRR, hallucination rate, answer similarity (diagnostic only), pairwise, regression baseline, variance, and drift checks.
- Online judges sample 10% plus all abstained, escalated, or edited runs.
- The code layout follows ports and adapters.

Evidence:
- Built-in middleware list ([docs](https://docs.langchain.com/oss/python/langchain/middleware/built-in)).
- `ToolStrategy.handle_errors` does not validate raw dict schemas ([docs](https://reference.langchain.com/python/langchain/agents/structured_output/ToolStrategy/handle_errors)).
- `evaluate_comparative` takes `randomize_order` ([docs](https://docs.langchain.com/langsmith/evaluate-pairwise)).
- `InMemoryRateLimiter` is per process ([docs](https://docs.langchain.com/langsmith/handle-model-rate-limiting)).
- Experiments can be compared against a pinned baseline ([docs](https://docs.langchain.com/langsmith/analyze-an-experiment)).
- openevals provides an embedding similarity evaluator ([README](https://github.com/langchain-ai/openevals/blob/main/README.md)).
- Malatesha chose all of these, 2026-10-06.

Debug steps: None.

Fix: Updated `AGENTS.md` (agent build and middleware, customer history, eval metric catalog, code structure), `architecture.md` (layer table), `prd.md` (customer history), and `explanation.md`.

## 2026-10-06 — FlashRank replaces the Torch cross-encoder; Neon replaces Render Postgres; dev/uat/prod branching

Status: decision

What changed:
- Rerank is `FlashrankRerank` with `ms-marco-MiniLM-L-12-v2`, not `CrossEncoderReranker`.
- Postgres is Neon, one branch per environment.
- Git flow: `feature/*` into `dev`, then `uat`, then `prod`, each by PR. After a release, `prod` is merged back into `main`, so `main` mirrors what is live.
- One LangSmith project and one Pinecone namespace per environment.
- RAG judges use openevals prebuilt prompts, and retrieval is scored by code against gold section ids.

Evidence:
- Render free: 512 MB RAM. Only one free Postgres per workspace, deleted 30 days after creation ([Render free](https://render.com/docs/free)).
- Pinecone hosted rerank on the free plan: 500 requests a month per organization ([limits](https://docs.pinecone.io/reference/api/database-limits)). That is too few for CI evals.
- FlashRank runs on ONNX with no Torch. MiniLM-L-12 is about 34 MB ([PyPI](https://pypi.org/project/FlashRank/0.2.10/)).
- Neon free: 10 branches per project ([Neon](https://neon.com/faqs/free-plan-limits-and-quotas)).
- Vercel Hobby supports a branch-based staging preview. Custom environments need Pro ([Vercel](https://vercel.com/docs/deployments/environments)).
- Malatesha chose all of these, 2026-10-06.

Debug steps: None yet. Phase 2 measures FlashRank's resident memory on a Render free instance before building on it.

Fix: Updated `AGENTS.md` (stack, retrieval shape, RAG evaluators, environments, branching, CI gates, docs list) and `architecture.md` (layer table, retrieval and deploy diagrams). If FlashRank does not fit in 512 MB, log a bug entry here and swap the reranker behind the `Reranker` port.

## 2026-10-06 — PRD round 4: labeled set size, step streaming

Status: decision

What changed: Slice 1 labeled set is about 40 cases (60% normal, 25% edge, 15% failure), split 10 judge calibration / 15 dev / 15 test. The console streams step progress, not draft tokens. The draft shows only after the output check.

Evidence: Malatesha, 2026-10-06, grilling round 4. The after-agent output check can replace a draft, so token streaming would show text that is later withdrawn.

Debug steps: None.

Fix: Updated `prd.md` (Quality program, Experience) and `AGENTS.md`. Q12 (exchange section) is still open.

## 2026-10-06 — PRD round 3: identity, catalog fields, release bar, roles, stale flag

Status: decision

What changed: The identity check moves from P1 to P0 (R14). The specialist binds each case to one customer by email or phone, and `lookup_order` is scoped to that customer from case state. Catalog rows gain category, sizes or variants, and in stock yes or no. R12 now points at a numeric release bar in `prd.md`. Only a lead approves, and never their own proposal (R22). A proposal is flagged stale after 24 hours and never auto-decided (R23). The open point on partial credit is closed, because REF-PARTIAL already says 50% store credit.

Evidence: Malatesha, 2026-10-06, grilling round 3. Before this, P0 order status already required an order-to-customer match while the identity check was P1, so the PRD contradicted itself.

Debug steps: None.

Fix: Updated `prd.md`, `AGENTS.md` (capability table, roles, CI gate), and `CONTEXT.md` (case customer, stale proposal, lead, catalog item). Still open: the handbook has no exchange section, and one is needed before P1 exchange.

## 2026-10-06 — Handbook is written here, not copied and not invented at runtime

Status: decision

What changed: Q2 is not “the model writes policy during a case,” and it is not a paste of Amazon or Flipkart. This project writes an original Northstar handbook. The topics match common marketplace practice: return window, condition, final sale, damage, shipping, warranty, cancel-before-ship.

Evidence: Malatesha, 2026-10-06. Copyrighted policy pages are not a source we may copy.

Debug steps: None.

Fix: Files under `data/policy/` are the frozen handbook. Ingest those files only. The agent abstains when they do not cover the question.

## 2026-10-06 — Case desk, and catalog facts are not RAG

Status: decision

What changed: The specialist console is a case desk. Customer words on the left. Draft, citations, order lines, and the proposal on the right. Catalog questions are answered from Postgres catalog rows. Handbook questions are answered by retrieval over `data/policy/`. Anything absent from those sources is an abstain.

Evidence: Malatesha accepted the case desk on 2026-10-06 and required product questions to refrain when the platform has no record.

Debug steps: The handbook files were already written under `data/policy/` in the previous session. They are not still waiting to be generated.

Fix: Recorded in `prd.md`, `CONTEXT.md`, and `AGENTS.md`. Catalog seed rows are still to be loaded into Postgres at implementation. The handbook text is already the source of truth.

## 2026-10-06 — Specialist console and a hard token budget

Status: decision

What changed: Slice 1 is specialist-operated. Customer and order rows live in Postgres and are checked before a purchase fact is spoken. Token use fails closed: 20 retrieved, at most 4 chunks in the prompt, last 6 messages, one judge call that does not see tool logs.

Evidence: Malatesha accepted Q1 and Q3 on 2026-10-06. LangSmith records token and cost on runs. LangChain middleware can limit model calls.

Debug steps: None.

Fix: Recorded in `AGENTS.md` and `prd.md`.

## 2026-10-05 — Vector store is Pinecone, not Chroma

Status: decision

What changed: Earlier design used a local Chroma index for policy chunks. The project now uses Pinecone through `langchain-pinecone` `PineconeVectorStore`.

Evidence: [Pinecone vector store](https://docs.langchain.com/oss/python/integrations/vectorstores/pinecone). Product decision to host the index separately from the API process.

Debug steps: None. This is a design change before implementation. No Chroma code exists to migrate.

Fix: Policy ingest writes to Pinecone with `section_id` metadata. Chat history does not go in the index. Rerank stays a local cross-encoder on the top-20 Pinecone hits. Embedding dimension and the index dimension must match.

## 2026-10-05 — Conversation memory is Postgres, not SQLite or RAM

Status: decision

What changed: Earlier design used SQLite locally and Postgres only in deployment. Production memory is now Postgres in both places.

Evidence: [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence) states `MemorySaver` / `InMemorySaver` keep checkpoints in RAM and lose them on restart. [Checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers) document `PostgresSaver` for thread state. [Add memory](https://docs.langchain.com/oss/python/langgraph/add-memory) documents `PostgresStore` for cross-thread memory. HITL resume needs the same `thread_id` after the process restarts.

Debug steps: None yet. Expected failure if someone uses `MemorySaver` in the API: the approve call returns no pending interrupt after a restart.

Fix:

- `PostgresSaver` or `AsyncPostgresSaver` for the thread, including the refund interrupt.
- `PostgresStore` for cross-thread user facts. Namespace includes the user id.
- Orders and tickets are ordinary Postgres tables.
- Call `setup()` once on an empty database.
- `thread_id` must fit the checkpointer column. The persistence docs warn that an oversized `thread_id` raises a database error.

## 2026-10-05 — Trajectory scorer name

Status: decision

What changed: A LangChain video names `evaluate_extra_steps` and `evaluate_unmatched_steps`. Those names are not on the current guide.

Evidence: [Evaluate a complex agent](https://docs.langchain.com/langsmith/evaluate-complex-agent) publishes `trajectory_subsequence`. Reading the loop: expected steps must appear in order; extra actual steps are skipped and do not reduce the score. If the reference list is longer than the actual list, the sample returns `False`.

Debug steps: Compared the video transcript to the current docs page before writing the eval section.

Fix: Implement `trajectory_subsequence` as published. Add a separate `extra_step_count` so wasted tool calls still show up. Do not invent the video’s function names in code.

## 2026-10-05 — Refunds stay behind approval

Status: decision

What changed: The Chinook sample refunds inside the graph and uses `config={"env": "test"}` to mock the write. Northstar does not.

Evidence: Same guide’s refund path writes when invoked. No `interrupt` in that sample.

Debug steps: Read the refund subgraph section of the guide before copying it.

Fix: Eval examples that should create a ticket set `hitl_decision: approve`. Examples that should only propose a refund end at `awaiting_approval`. A ticket without a resume is a failed safety check.
