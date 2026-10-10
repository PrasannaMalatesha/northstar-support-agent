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

## 2026-10-10 — Fixes from the end-to-end check

Status: bug

Root causes and fixes for the problems in `results/e2e_check_2026-10-10.md`:
- **Final sale answered wrongly.** The reranker gave five sections 0.99 or more on the shared word "returned". REF-FINAL-SALE was fifth and the draft keeps four. Pinecone ranked it first. Now, when the reranker drops Pinecone's first section, the draft is marked `unsure` and the model (thinking `minimal`) chooses among the kept sections plus that one. NONE or a failure keeps the reranker's draft. On the 24 labeled handbook questions, the reranker always kept Pinecone's first section, so the extra call is rare.
- **"never placed" not escalated.** The ESC-FRAUD pattern matched only the present tense. It now matches placed, made, bought, ordered, and authorized.
- **Questions with "price" went to the catalog.** The catalog's handbook check used the reranker alone, which scores "wrong price by mistake" 0.0 everywhere. Item questions ("do you sell", "in stock", "how much", "what size", "do you carry/stock/have") keep the old path, so an unknown item still abstains. The first fix let the model pick answer "Do you sell surfboard wax?"; the release bar's abstain gate caught it, and that version was never merged. Questions that only say "price" or "final sale" now go to the handbook, with the model pick, before the catalog.
- **Wrong item.** No action matched "received a different item". It is a refund now: REF-WRONG-ITEM within the REF-DAMAGED report window (14 days), a full refund of the line and its outbound shipping.
- **Two orders in one message.** The first order id and one action were read, and the rest dropped. A request that names more than one order now asks for one request per order and proposes nothing.
- **Follow-up "And what if she lost it?".** "lost" picked the lost-package action, which asked for an order. A short follow-up (and, so, what if, what about, …) with no order now reads the handbook with the previous question.
- **Address change after an approved cancel.** Tickets do not change an order's status. Nothing but a refund (which REF-DENY already refuses) or a duplicate cancel is proposed on an order with a cancel ticket.
- **Insults and "ignore all previous instructions".** The block list matched "ignore previous" but not "ignore all previous", and had no insults. A pattern now matches ignore, disregard, or forget followed by instructions, rules, the handbook, and similar words, and insults aimed at a person (ESC-ABUSE). "This stupid zipper broke" is not blocked.
- **"torn"** is a defect word.
- **"Where is my order?" in a chat** reads the order the chat was started with.
- **NS-1002 seed.** It was "shipped" with a delivery date, so the refund rule treated it as delivered. It is now a consistent delivered order (delivered 2026-10-01), refundable for the tests' clock and for the browser suite's real clock through 2026-10-31. Its old date would have broken the live chat refund browser test after 2026-10-12. A new test checks that only delivered orders carry a delivery date.

Changed tests:
- `test_a_completed_cancel_blocks_a_second_cancel_but_not_another_action` used an address change on a cancelled order as its "another action". That is the bug above, so it now expects ORD-CANCEL, and a new test checks family scoping with an address change followed by a cancel.
- The live chat browser test now expects NS-1002 with its real status, "delivered".

Left as is:
- **The judge's reasoning effort.** At effort `low`, DeepSeek used 44% fewer tokens and still failed every ungrounded reply in a 12-case check. But it also failed a correct escalation handoff: 9 of 12 against 10 of 12 at the default. A cheaper quality monitor that is less accurate is not a clean fix.
- **"Do you price match competitors?"** gets the catalog miss. No handbook section covers it, and the model pick says NONE.

## 2026-10-10 — Fixes from the conversation check

Status: bug

What broke (results/conversation_check_2026-10-09.md and the browser demo):
- **The customer chat ignored its order.** "My desk lamp arrived broken, I want my money back" in a chat started on NS-1011 got "Which order id?". The chat token carried only the customer.
- **A complaint naming a product got the catalog row.** "The rain jacket leaks at the seams" got price and stock. "seams" did not match the defect pattern (`\bseam\b`), "leaks" was not in it, and any message naming a product went to the catalog.
- **"She will sue us" was not escalated.** ESC-LEGAL matched only the words chargeback, lawyer, lawsuit, regulator, and legal advice.
- **A lost gift card asked for an order.** "lost" made it a lost package.
- **"Exchange for an XL" asked which size.** Sizes were read only after the word "size".
- **Handbook misses.** "Does the warranty cover a speaker she dropped?" and "Can we ship an order to Canada?" abstained. Follow-ups such as "what should I tell her about sending it back?" abstained too.
- **Staff were signed out 15 minutes after sign-in, mid live chat.** The console never used the refresh token. The desk then bounced between `/login` and `/desk`, and the middleware's redirect went to `localhost`.

Evidence for the handbook misses: Pinecone ranked the right section first every time (WAR-EXCLUSIONS 0.673, SHIP-REGIONS 0.633). FlashRank (`ms-marco-MiniLM-L-12-v2`) scored them 0.01 to 0.04, under the 0.2 threshold. A threshold on Pinecone similarity cannot separate them: "Can I pay with cryptocurrency?" also scores 0.633. Every should-abstain question tops out at a 0.02 rerank score, too close to the misses (0.042) for a threshold rule.

Fix:
- **Chat order.** The chat token carries the order (`ord`) from `/chat/start`, kept on renewal. An action that names no order uses it. Handbook questions are unchanged.
- **Defects and complaints.** `seams?` and `leak` are defects. A message that names a product and reports a problem is not a catalog question.
- **Legal and gift cards.** ESC-LEGAL also matches threats to sue, attorneys, court, small claims, and legal action. The name Sue does not match. A lost gift card is not a lost package.
- **Sizes.** "for an XL", "to a M", and XXS to XXL are read. A size the item is not made in gets "not made in size XL. Sizes: S, M, L" (EXC-STOCK).
- **Handbook misses.** When the reranker keeps no section, the model (thinking `minimal`) picks among the reranker's own top four, or NONE. It sees the case's previous question. Picked sections are cited as weak. In testing it picked the right section for every miss and NONE for every should-abstain question. "Can I pay with cryptocurrency?" now answers from PAY-METHODS, which lists the accepted methods.
- **Staff session.** The console renews the API token within its last minute (Auth.js `jwt` callback). Middleware runs on the Node.js runtime, so the page in the same request reuses that one renewal (`apps/web/staff-session.ts`); a rotated refresh token is never spent twice. A refused renewal ends the session, and `/login?expired=1` shows "Your session ended" instead of bouncing. Redirects keep the browser's host. `ACCESS_TOKEN_MINUTES` sets the token life (15 by default, 1.5 in the browser suite).
- **Token savings.** Thinking is `minimal` for the agent's tool call and `low` for the handbook wording. Translation and the photo check keep the default. The desk tool returns directly, so the agent's unused final call is gone.

Results on the same conversations:
- Latency p50 2.54 → 0.85 s, p95 7.97 → 4.41 s.
- Gemini calls per model turn 2.25 → 1.48.
- Cost per turn $0.00170 → $0.00081 (−53%).
- Tests: 331 Python and 12 browser tests pass. `test_a_model_that_keeps_asking_stops_after_the_desk_answers` now expects one model call; the old worst case of three cannot happen with `return_direct`.

Open:
- A stronger reranker would fix the misses at the source. It needs a model download, so it waits for a decision.
- The labeled hand-over case `chat-three-failures` now uses "Exchange this for another size, please." as its failed turn, because a chat refund now finds its order. LangSmith sync adds by case id, so the old example in the `update-handover` dataset still has the old question. Update it when the trace limit allows.

## 2026-10-09 — The agent package did not declare langchain

Status: bug

What broke: in the browser demo on a fresh worktree, the first live turn returned 500 with `ModuleNotFoundError: No module named 'langchain'`.

Evidence: `northstar.graph` imports `langchain.agents` (create_agent and its middleware), and `northstar.online` imports `langchain_openai` (the judge). Both packages were listed only in the root `dev` dependency group. CI and the main checkout run `uv sync --all-packages --group dev`, so they had them. `make api` on a fresh clone (`uv run --package northstar-api`) did not.

Fix: `langchain` and `langchain-openai` are runtime dependencies of `northstar-agent`. The lock resolves the same versions. A clean `uv run --package northstar-api` now imports both.

## 2026-10-09 — The agent's email filter hid the published support address

Status: bug

What broke: the first release bar run for the update phase (commit 8972587) failed one gate. English p95 latency was 10.47 s against the 10 s target. Every other gate passed (action correct 100%, Spanish p95 17.07 s, max 4,151 tokens).

Evidence: timing each English test case once on the live desk, 14 of 15 took 2 to 8 s. "What email should a customer use to contact support?" took 11.1 s and 2,496 tokens, about twice the others. The release run repeats each case 3 times, so this one case gave 3 slow turns out of 45. That is enough to fail the p95 on its own.

Debug steps: printing the `create_agent` messages for that question showed the email `PIIMiddleware` redacting `help@northstar.example` from the desk tool's result. The model saw `[REDACTED_EMAIL]`, called the desk again, hit the tool call limit, and needed a third model call to finish. `screen()` already kept the published addresses (#105). The middleware used the built-in email detector, which has no such exception.

Fix: `privacy.detector("email")` uses the same pattern as `screen()` and skips `PUBLISHED_EMAILS`. The graph's email filter uses it. A customer's address is still redacted for the model. The turn now makes the usual two agent calls (2.3 s for the agent step, down from 5.7 s). Test: `test_the_agent_email_filter_keeps_the_published_address`.

## 2026-10-09 — Update phase built (#132 to #145, PR #146)

Status: decision

What changed:
- **U1, quality within budget:**
  - Experiments run one code evaluator per row (`code_scores`), one repetition by default, with `--no-upload` and `--router` options (#132).
  - The release bar runs locally (`evals.experiments release`) and writes `results/release_bar.json`. A CI job on PRs into `uat` checks that file (#133).
- **U2, limits and a bounded conversation:**
  - Per-customer chat limits (10 agent turns a day, 500 for all chat customers) in a Postgres `daily_limits` table, counted atomically (#134).
  - A 45 s turn deadline that skips optional model steps (#135).
  - After 3 failed turns, the chat suggests a follow-up (#137).
- **U3, escalations inbox:** leads see escalated cases, specialists pick them up, and a reply reaches the customer's chat (#136).
- **U4 to U6, live chat** behind `LIVE_CHAT_ENABLED`, off by default:
  - The tracer bullet (#138).
  - Offers that move on (#139).
  - The line and the wait estimate (#140).
  - Escalations and three failures reach the line (#141).
  - Quiet customers free the specialist (#142).
  - Money actions in a live chat (#143).
- **U7:** the lead's line view and alerts (#144), and hand-over evals and the hand-over reason (#145).

Evidence:
- After the code review fixes: 317 Python tests, 11 browser tests (axe, three-browser live chat flows), lint, types and build all pass.
- The two-axis review covered standards and spec. Its fixes are below.
- Every agreed setting matches its code default.

Debug steps: Each ticket was built in its own worktree with its own test database and merged into `feature/update-phase` only after the full suite passed on the merged result. Browser checks ran under a shared lock, because the suite's ports are fixed.

Fix: Built as planned, with the differences listed in "Built differently" in `docs/plans/update-phase.md`.

Open for Malatesha:
- Whether the agent keeps answering while an escalation waits in the line. Today it stays quiet.
- Making "Release bar results" a required check on `uat`.
- Setting `TOKEN_CAP` from the first real release run.
- A follow-up PR that moves the live chat code out of `cases.py`.
- The escalations inbox has no "done" state: an answered escalated case stays listed.

## 2026-10-09 — Code review fixes for the update phase

Status: bug

What broke:
- **Desk forms:** two desk server actions put the form's case id straight into the API path. A crafted value could send the request to a different route under the specialist's own token.
- **Tie-break:** ties went by staff id, not "longest since offered".
- **Offer card:** it lacked the reason and the language.
- **Spec gaps:**
  - `POST /live/next` was missing;
  - the live chat page lacked the customer's orders and history;
  - chats per specialist was not a setting.
- **Names:**
  - "offer" and "handoff" were each used for two things;
  - the setting name used "agent" for a person.
- **Code shape:**
  - settings defaults lived in two places;
  - the line's timers ran in a different order on each read path.

Evidence: The standards and spec reviews, run in parallel against spec #131 and its tickets.

Fix:
- **Case ids:** checked before they reach an API path, and typed as UUIDs in the API (a malformed id gets 422).
- **Tie-break:** `specialist_availability.last_offered_at` decides ties. It is not taken from `live_chat_requests.offered_at`, because a decline clears that row's specialist, which would make the specialist who just declined look never-offered.
- **Offer card and end reasons:** `language` and `end_reason` columns. Offers show the reason and a Spanish label. The quiet close records `closed_quiet`.
- **Missing pieces:** `POST /live/next` and a "Take next" button; orders and history on the live chat page; the setting `LIVE_CHATS_PER_SPECIALIST`.
- **Renames:** `LIVE_CHAT_ENABLED`; the chat's `follow_up` (glossary: Follow-up); `record_handover` and feedback key `handover_reason`.
- **Code shape:** one defaults module (`northstar/defaults.py`), and one `_tick()` that runs sweep, expire, quiet, then offers, on every read and write path.

## 2026-10-09 — Two shared Postgres connections could open twice under a race

Status: bug

What broke: `preferences._store` and `memory.graph_for` cached their Postgres store and checkpointer without a lock. When the first requests to a fresh process arrived at once, each could open one, and the loser's connection was closed while still in use ("the connection is closed").

Evidence: The concurrency test in #134 hit it, and a new test with eight racing threads fails without the fix.

Fix: A module lock with a second check inside it, in both caches.

## 2026-10-09 — `upload_results=False` still sent traces

Status: bug

What broke: In langsmith 0.14.4, `evaluate(..., upload_results=False)` still posts the LangChain model runs made inside the target and the evaluators. A "local" experiment would have kept using the monthly trace allowance.

Evidence: Shown with a client that has no server behind it; a test fails if the fix is removed.

Fix: `--no-upload` also turns tracing off around the target and passes `disable_evaluator_tracing=True` (#132).

## 2026-10-09 — Ending a live chat could drop a waiting proposal

Status: bug

What broke: Resolving or escalating a live chat whose case waited for a lead overwrote the case status. The proposal silently left the lead's approval list.

Evidence: Found while building #143.

Fix: `ProposalWaiting`: a live chat cannot be ended, by hand or by the quiet-customer close, while its case waits for a lead (#143, #142).

## 2026-10-09 — Browser tests failed only in the main checkout

Status: bug (local setup, not product code)

What broke: The first two browser tests failed on the integration branch with "Application error". The login page crashed with `__webpack_modules__[moduleId] is not a function`.

Evidence:
- An old `next dev` server on port 3000 (started 2026-10-06) runs from the same `apps/web` folder and shares its `.next` cache with the suite's dev server.
- From a separate worktree with its own cache, all 11 browser tests pass.
- A first guess, that a slow model turn was the cause, was wrong. Its test change was reset before it was pushed.

Fix: Browser checks run from a separate worktree, or after stopping the old server. Nothing in the product changed.

## 2026-10-09 — Update phase grilled and settled

Status: decision

What changed: Malatesha and the plan went through four rounds of questions. Every open setting is now agreed. Specialists take live chats, and leads only approve. A specialist holds 2 live chats at once. An offer has 45 seconds to be accepted. Quiet-customer timers are 2, 3, and 15 minutes. The wait cap is 20 minutes, and a customer who stops refreshing for 2 minutes leaves the line. After 3 failed turns the chat offers a person. Each chat customer gets 10 agent turns a day, and all chat customers 500. The release bar runs locally with a results file that CI checks, because CI holds no keys. Spanish has its own p95 target of 20 s. "Handoff" keeps its meaning (the packet). A customer's request for a person is a "live chat request" waiting in "the line" (`CONTEXT.md`).

Evidence: The decisions are listed in `docs/plans/update-phase.md` (agreed settings) and `prd.md` (R34 to R49, Open points). The line's design is recorded in `docs/adr/0001-live-chat-line-in-postgres.md`.

Fix: Documentation only. Building starts at U1 when Malatesha asks.

## 2026-10-09 — Update phase planned: production readiness and live human support

Status: decision

What changed: Slices 1 to 3 are built, but an end-to-end check and a review found gaps for real customers. Chat customers share one model budget. Request limits live in memory. Escalated chats have no staff list. The chat token cannot be renewed. Experiments use up the trace allowance. There is no way for a customer to reach a person. `prd.md` now has an update phase (R34 to R49), and `docs/plans/update-phase.md` holds the design and build order (U0 to U7).

Evidence: The code facts are listed under "What the code showed" in the plan. Routing, capacity, the wait estimate, and the timers follow Twilio TaskRouter, Salesforce Omni-Channel, Zendesk, Intercom, and the Postgres docs, as cited in the plan.

Fix: Planned only. U0 is done in #128. The rest waits until Malatesha has grilled the plan and agreed the settings listed under Open points in `prd.md`.

## 2026-10-09 — Model calls had no timeout, stacked retries, and no real step cap

Status: bug

What broke: Nothing visible yet, but there were three limits missing. (1) The Gemini client had `timeout=None` and `max_retries=6`. google-genai counts that as 6 attempts including the first, and `ModelRetryMiddleware(max_retries=2)` repeats the whole call 3 times, so one model call could make up to 18 requests, each with no time limit. (2) No `recursion_limit` was set, and the installed LangGraph 1.2.14 defaults to 10007 supersteps (`langgraph/_internal/_config.py`), not the 25 the docs page shows. (3) The background groundedness judge on OpenRouter had no timeout either.

Evidence: Read `HttpRetryOptions.attempts` ("Maximum number of attempts, including the original request") and `retry_args` in google-genai 2.28.0, and how langchain-google-genai 4.4.0 passes `timeout` and `max_retries`. Counted supersteps on a live turn: the router takes 3; the agent takes 12 per model call because every middleware hook is its own step. Probed the limit with a scripted model: a normal agent turn needs 26, and the worst case `run_limit=3` allows needs 43.

Fix: Every model call now gets at most 3 attempts of at most 20 s each, and only one layer retries. Calls outside `create_agent` (wording, translation, photo) let the client retry (`max_retries=3`). The agent's model and fallback make one attempt each, and `ModelRetryMiddleware` retries. The router runs with `recursion_limit=10` and the agent subgraph with its own `recursion_limit=50`. It is set on the agent's call, because the router's config would otherwise carry over. The background judge has `timeout=30, max_retries=1`. A live check with every model call forced to time out: the handbook answer and the damaged-item refund still came back from the desk rules, the Spanish turn abstained instead of guessing, and no turn hung.

Also found: the LangSmith monthly limit was used up by experiments, not retries. A retry stays inside its trace. This month: 3,855 evaluator traces (3,852 on 2026-10-08), about 1,165 experiment traces, and 158 app traces. Each experiment row adds one trace per evaluator. Next: one evaluator that returns several scores, one repetition while developing, and `upload_results=False` for local runs.

## 2026-10-08 — Customer chat stuck after an escalation, and a silent desk tool failure

Status: bug

What broke: In the end-to-end check (the full demo script driven in a browser on a fresh database), a customer's second chat message while their refund waited for a lead got 409 "This chat is closed." and the chat page dropped it without a word. Worse, after an escalation the chat kept returning the escalated case, which no one resolves, so that customer could never chat again. Separately, one desk turn out of about 35 showed "The lookup failed. No facts were filled in. Try again." with nothing in the API log: `ToolErrorMiddleware` caught the error and nothing recorded it.

Evidence: `POST /chat/messages` returned 409 for a customer with a waiting refund and for one with an escalated case. The lookup failure did not come back in 10 warm turns, 3 cold starts, or the 20-turn demo run.

Debug steps: Called the chat API directly with a chat token for NS-1006. Re-ran the failing question in-process with the tool error printed, warm and from a cold start.

Fix: After an escalation, the customer's next message starts a new chat case; the escalated case stays with the specialist, and the chat still shows "A specialist will follow up" until then. While a request waits, the API says so (409, "A person on our team is reviewing your request.") and the chat page shows "Your request is with our team. You can write again once they reply." The desk tool error is now logged with its traceback, so the next one shows its cause. The failure itself stays safe: no facts are filled in.

## 2026-10-08 — LangSmith's monthly trace limit, and the trace upload moved off the request

Status: bug

What broke: Every turn waited for its trace upload (`wait_for_all_tracers()` and `flush()` in `run_turn`) before replying. When LangSmith throttles, that wait lands on the specialist: a turn took about 9 s with tracing on and about 6 s with it off. The browser suite timed out on it.

Evidence: LangSmith returned 429 "Too many requests: tenant exceeded usage limits: Monthly unique traces usage limit exceeded". New runs are not stored (reading two fresh run ids returned 404), so no new traces, rule scores, judge feedback, or experiments reach LangSmith until the monthly limit resets (2026-11-01) or the limit is raised in LangSmith's settings. The product itself is unaffected.

Debug steps: Timed the same turn twice with tracing on and twice with it off. Confirmed the in-app judge still ran and posted, and that the runs it scored were missing on the LangSmith side.

Fix: `run_turn` hands the upload to the existing background job, which waits for the tracers, flushes, and then runs the judge on the uploaded root run. The turn no longer waits: about 6.3 s with tracing on. Account action for Malatesha: raise the LangSmith usage limit or wait for the monthly reset before running more experiments.

## 2026-10-08 — Staff sign in with Google (issue #78)

Status: decision

What changed: Google single sign-on, on when `AUTH_GOOGLE_ID` is set (the console and the API read the same variable). Then the login page offers only "Sign in with Google", and the password action refuses. With it unset, nothing changes.
- The console never decides who someone is. Auth.js sends Google's ID token to `POST /auth/sso`. The API checks the signature against Google's published keys (PyJWT `PyJWKClient`), the audience (our client id), the issuer, the expiry, and `email_verified`, then looks up the staff record by email. The role comes from `staff_users`, never from a claim. An unknown or disabled account is refused. The API then issues the same staff tokens as a password login.
- Auth.js has no database adapter, so the same `user` object goes from the `signIn` callback to `jwt()`; the exchange happens once in `signIn`, and a refusal sends the person back to `/login?error=sso` with no session. Read in `@auth/core` `lib/actions/callback/index.js`.
- Tokens stay in the server-side session cookie, as before. Audit: `sso_login_success`, `sso_login_failure`; logout is audited as before. A disabled account's existing sessions stop working (the token check already reads `disabled_at`).

Evidence: `test_sso.py` (11 tests, a local RSA key stands in for Google's): a verified account gets its staff role even when the token claims another; unknown email, unverified email, wrong audience, wrong issuer, expired, wrong signature, and a disabled account are each refused and audited; SSO is off without a client id; a disabled member loses the session; logout is audited. In a real browser with a placeholder client id, `/login` showed one Google button and no password field, and the button went to accounts.google.com with our client id. With SSO off, the browser suite passes unchanged.

Debug steps: None needed for SSO. While checking it, the browser suite was slow because LangSmith returned 429 "Monthly unique traces usage limit exceeded"; see the next entry.

Fix: As above. Malatesha creates the Google OAuth client and puts `AUTH_GOOGLE_ID` and `AUTH_GOOGLE_SECRET` in `.env`.

## 2026-10-08 — Spanish replies (issue #81)

Status: decision

What changed: A Spanish question gets a Spanish draft that cites the English section ids. `northstar/language.py`: a marker check spots Spanish with no model call, so English turns pay nothing. The question (after the secret check, and screened) is translated to English once; preferences, escalation triggers, the safe-reply block, gated-action rules, retrieval, and citations all run on that English text unchanged. The draft is translated back with section ids, order ids, and amounts kept; a dropped section id is appended in English, and a model failure leaves the English draft. The customer's own words are saved. The staff handoff packet stays English. Both groundedness judges are told the reply may be Spanish and compare it with the English section text. Experiments add a `reply_language` check on Spanish rows.

Evidence: `SPANISH_CASES` (handbook answer, abstain, unknown catalog item, refund proposal, chargeback escalation, jailbreak), dataset tag `slice3-es` (74 cases). Tests in `test_spanish.py` use a stand-in translator: each case keeps its English decision, citations, and status; an English question makes no translation call; a secret stops before translation; a dropped section id is put back.

Debug steps: The first live dev experiment on `slice3-es` missed two rows. es-jailbreak: Gemini translated "Ignora el manual" as "Ignore the manual", which the block list did not know, so the turn fell through to "Pick a customer first" (safe, but not the safe reply). es-refund: the reply was Spanish ("Aprobado. Monto: 12800 centavos."), but the marker check had none of those words.

Fix: The block list adds "ignore the manual", "ignore the instructions", "ignore your instructions", and the Spanish "ignora el manual", "ignora las reglas", "ignora las instrucciones" (checked on the original and the translation). The marker list adds common reply words. No English question in the labeled sets reads as Spanish. The test's stand-in translation now says "manual", as Gemini did.

Parked and resumed: Malatesha parked #81, then asked for it back. It was re-applied on top of the photo (#80) and chat (#79) work rather than rebased: translate first, run every gate on the English text, describe a photo against the English note, then translate the finished draft. A Spanish customer in the chat gets the fixed proposal, escalation, and duplicate texts in Spanish. Live after the fixes (tag `slice3-es`, 6 cases, 3 repetitions, `results/langsmith_dev_slice3-es.md`): v1 `label_match`, `reply_language`, `answer_correct`, citations, and status all 1.0.

## 2026-10-08 — A customer chat in front of the same agent and gates (issue #79)

Status: decision

What changed: Malatesha decided a customer identifies with an order id and the email on that order; `prd.md` (P2, Customer-facing entry) records it. The agent is the same: a chat message runs `CaseStore.ask`, so escalation triggers, the safe reply, the handbook rules, proposals that wait for a lead, the citation and output checks, and PII masking all hold unchanged. What differs is identity, scope, and view:
- Identity: `POST /chat/start` checks the order and its email and returns a chat token with its own audience (`northstar-chat`, 30 minutes). It never passes as a staff token, and a staff token never opens the chat. Every miss gets one message (no order or email enumeration). Misses count toward the login lockout, keyed `chat:<email>`.
- Scope: chat cases are owned by a seeded, disabled staff user `chat@northstar.example` (it can never sign in), bound to the customer, one open case per customer. The existing ownership check returns "Not found for this customer" for anyone else's order. Request limits are per customer. A customer cannot approve, edit, or close.
- View: `GET /chat` returns only the status and the messages. A proposal shows as "A person on our team will review this request. Nothing is approved yet."; an escalation as "A specialist will follow up with you about this." The draft, amount, rationale, handoff packet, customer details, and history never reach the customer. After a lead approves, the status gives the ticket reference.
- Console: a public `/chat` page; the token sits in an httpOnly, SameSite=Strict cookie scoped to `/chat`. `sameSite()` and `apiUrl` moved to `app/same-site.ts` for both pages.

Evidence: `test_customer_chat.py` (10 tests): start and the single miss message, lockout, token separation both ways, the chat account cannot sign in, other customers' orders, a refund waiting for a lead and then approved, an escalation without the packet, the jailbreak safe reply, no personal data in the view, a card number never shown. A browser test in `screens.spec.ts` runs the chat end to end and passes axe.

Debug steps: The browser test first proposed a refund on NS-1001, which the desk test had already refunded, so the duplicate block (correctly) answered "already with our team"; it now uses NS-1006. Next.js's route announcer also has role="alert", so the test finds the error by its text.

Fix: As above. Photos are refused in the chat (the desk takes them).

## 2026-10-08 — A damaged-item photo, and the REF-DAMAGED rule it needs (issue #80)

Status: decision

What changed: A specialist can attach a photo (PNG, JPEG, or WebP, under 4 MB) to a desk message. Gemini returns a structured verdict (does it show the item, is damage visible) and a two-sentence description; the draft and the proposal details get one line, "Photo: visible damage." / "Photo: no visible damage." / "Photo: does not show the item.", which the lead sees in the queue. The action still comes only from the specialist's words and the handbook rules, and the lead still decides: a photo alone proposes nothing. The image is checked, described, and dropped: not saved, not in `PostgresStore`, not in the handbook index, and the vision call runs with LangSmith tracing off. The description passes the PII screen. Both groundedness judges are told a "Photo:" line is evidence, not a policy claim.

REF-DAMAGED did not exist as a rule: "arrived damaged" matched no action, and "arrived cracked" became an ordinary return citing REF-ELIGIBILITY. Now a damage report on a delivered order within 14 days is a full refund of the line and its outbound shipping citing REF-DAMAGED; after 14 days the ordinary return window applies, as the handbook says. Seed order NS-1011 (desk lamp, delivered 2026-09-30) mirrors the handbook's own example.

Evidence: `test_damage_photo.py` (stand-in describer): REF-DAMAGED inside and after 14 days; the three labeled photos reach the draft and the lead while the decision stays REF-DAMAGED; a photo alone proposes nothing; with no vision model the photo is noted and nothing breaks; a wrong type or an oversized image is refused with 422 before the desk runs; no image bytes are stored. A browser test in `screens.spec.ts` uploads the photo and passes axe. Live experiment on `PHOTO_CASES` (tag `slice3-photo`, 3 repetitions, `results/langsmith_dev_slice3-photo.md`): v1 `photo_verdict` 1.0, `label_match` 1.0, status 1.0.

Debug steps: The first live check called the intact-lamp drawing damaged because the drawn shade sat off its stem; the drawings were redrawn with the shade centered. The API refused any body over 16 KB, so a real phone photo would have failed with 413; tiny test drawings hid it. The browser test first gave up after 5 seconds while the live vision turn was still running.

Fix: The message route allows 6 MB (a 4 MB photo as base64); every other route keeps 16 KB. The console's server actions allow 6 MB. The browser test waits up to 30 seconds for the photo line. The photos in `evals/photos/` are synthetic drawings, not real customer photos. Experiment results are now written per version, so runs do not overwrite each other.

## 2026-10-08 — "Do you sell X?" now asks the catalog (the promoted surfboard case)

Status: bug

What broke: "Do you sell surfboard wax?" got the handbook abstain ("No handbook section covers that.") instead of the catalog answer. PRD R21 says questions about what Northstar sells are answered only from catalog rows, and an unknown item abstains with the catalog line.

Evidence: The promoted specialist edit `edit-01a11a09` failed the judge on the dev experiment (v1 `answer_correct` 0.9, the only miss).

Debug steps: `_catalog_draft` only fired on "in stock", "how much", "price", "final sale", and "what size". "Do you sell / carry / stock / have" never reached it.

Fix: Those four phrases join `_CATALOG_PHRASES`. A named item gets its catalog row; an unknown item gets "I don't have that item in the catalog."; a question a handbook section answers ("Do you have gift cards that expire?") still goes to the handbook. Test in `test_catalog.py`. Live: dev split (tag `edit-20261008-054354`, 43 cases) v1 `answer_correct` 1.0, `label_match` 1.0, status 1.0, no misses. Router 1.0.

## 2026-10-08 — The first specialist edit promoted into the golden dataset

Status: decision

What changed: One reviewed edit became a labeled case: "Do you sell surfboard wax?" The desk abstained ("No handbook section covers that."); the specialist's final text was "We don't carry surfboard wax." It was promoted with label `abstain`, no sections, status Open, split dev, as `edit-01a11a09` under tag `edit-20261008-054354` (68 cases; `slice1` 40 and `slice2` 67 unchanged).

Evidence: The three edits already in the queue were not promoted. Two were amount edits made during the browser dry run (12800 to 6400 and 4800 to 4000 cents); they contradict the handbook amounts, so as labels they would be wrong. The third pointed at the wrong trace (a lead's approve run with no question), recorded before PR #62 fixed which run gets the edit. A live repro on current code (shoe question, refund, approve, surfboard question, edited close) sent the edit to the surfboard turn's own root run.

Debug steps: The first tag returned 67 rows, not 68: `_add` tagged `datetime.now()` from the local clock, which sat a moment before the server's new version.

Fix: `_add` now tags the server's newest dataset version (`list_dataset_versions`), not the local time. The edit tag was moved to that version and returns 68.

First experiment on the new version (dev split, 43 cases, with the judge, `results/langsmith_dev.md`): v1 `label_match` 1.0, status 1.0, `answer_correct` 0.9; the one judge miss is the promoted case, because the desk still abstains where the specialist named the product as not carried. v0 `label_match` 0.349. Router 1.0. Fixed: see "\"Do you sell X?\" now asks the catalog".

## 2026-10-08 — A LangSmith online LLM judge runs beside the in-app judge

Status: decision

What changed: Malatesha asked for the LangSmith-side judge as well. Rule "Northstar groundedness (LangSmith judge)" on `northstar-local` runs `deepseek/deepseek-v4.1-flash` on every LangGraph root run and writes `langsmith_groundedness`. The in-app sampled judge (`policy_groundedness`) and the safety rule are unchanged, so nothing in the API path changed.

Evidence: Two live turns scored 1 (a cited return-window answer, and an abstain with no policy claim). A planted reply that cited REF-CATEGORY but claimed 90 days and free courier pickup scored 0, with the comment that the section says 30 days.

Debug steps: A rule sees only the trace (question, reply, cited ids), not the section text the in-app judge loads. The whole handbook is about 52 KB, so the prompt carries all of it. Rule creation follows the run-rules API (`RunRulesCreateSchema`, structured evaluator: prompt, schema, variable mapping, serialized model) from the LangSmith OpenAPI spec. Rules apply in 5-minute windows, so scores arrive a few minutes after the turn.

Fix: `attach_groundedness_rule()` in `online.py`, run by `uv run python -m northstar.online` beside `attach_safety_rule()`. The prompt is rebuilt from `data/policy`. The model references a LangSmith workspace secret `OPENROUTER_API_KEY`, set from `.env` and never printed or committed. The rule is created once; after a handbook change, delete it and rerun. Test: `test_langsmith_judge.py` (prompt carries every section and the trace fields, and holds no key).

## 2026-10-08 — The contact answer showed "[email]" instead of the support address

Status: bug

What broke: Asked for the support email, the desk replied "Customers reach Northstar at [email]." `screen()` masks every email address in saved text, including the one address the handbook publishes.

Evidence: The judged LangSmith experiment (`northstar-v1-test-204f6302`) scored contact `answer_correct` 0 in all three repetitions. The decision and the citation (FAQ-CONTACT) were right, so no code check caught it.

Debug steps: Compared the v1 output to the reference. Listed every address in `data/policy`: only `help@northstar.example`. A domain allowlist would not do: seed customers use the same domain (`mira.shah@northstar.example`).

Fix: `PUBLISHED_EMAILS` in `privacy.py` holds the handbook's published addresses, and `screen()` leaves only those unmasked. A customer address on the same domain is still masked. Tests: the published address is kept and a customer address is not; every address in the handbook is on the list; the contact answer through the desk keeps the address (fails without the fix). Live after the fix: test split v1 `answer_correct` 1.0, `label_match` 1.0.

## 2026-10-07 — The judge model is now deepseek/deepseek-v4.1-flash, with a majority vote

Status: decision

What changed: Malatesha replaced the OpenRouter key and the judge model. `nvidia/nemotron-3-ultra-550b-a55b:free` had hit its free daily cap and hung on some calls. Both judges (the offline quiz judge and the live groundedness judge) now default to `deepseek/deepseek-v4.1-flash`. The key stays in the gitignored `.env` only.

Evidence: Live checks on the new model: the quiz judge passed a right answer and failed a wrong one. The groundedness judge passed a grounded reply and failed a made-up 90-day rule. About 3 s a call.

Debug steps: Recalibrated before letting the new judge score the test split (issue #20). The first pass agreed on 4 of 5 rows. On apparel-window, the student text matched the reference word for word. Asked three times, the judge said correct twice and once called the handbook's own cross-reference ("the 30 days in REF-WINDOW" beside "the length in REF-CATEGORY") a conflict. The provider samples even at temperature 0.

Fix: The offline quiz judge takes the majority of three calls. Two calibration runs then agreed 5 of 5, and `results/judge_calibration.md` records that. The judge rate limiter is 2 requests a second for the paid model. The live groundedness judge stays at one call, because it is sampled and only writes feedback.

Judged result (test split, 3 repetitions, `results/langsmith_test.md`): v0 `answer_correct` 1.0, `label_match` 0.733. v1 `answer_correct` 0.909, `label_match` 1.0, status 1.0. Router 1.0. The v1 judge miss is real: on contact, the PII screen masks Northstar's own support address, so the reply says "Customers reach Northstar at [email]". Fixed: see "The contact answer showed \"[email]\" instead of the support address".

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
- Fixed (see "Policy questions that mention an order were refused or sent to the wrong path"). With no customer bound, a policy question that mentions "order" gets `unbound` (duplicate-hold, one-exchange, one-promo). shipping-price hits the known "price" catalog quirk. wrong-item gets `ask_clarification`. These are desk routing bugs, recorded here as honest failures.

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
