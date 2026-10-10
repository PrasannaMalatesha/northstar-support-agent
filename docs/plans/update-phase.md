# Update phase: production readiness and live human support

Status: built (2026-10-09). U0 is done in #128; U1 to U7 are built in tickets #132 to #145 on `feature/update-phase` (PR #146), plus the code review fixes. Every setting below was agreed with Malatesha in the grilling session. Where the build changed a name or a detail, this plan says so in "Built differently" at the end.

Source of scope: `prd.md`, update phase, R34 to R49. Terms: `CONTEXT.md` (agent, specialist, live chat request, live chat, line, offer, available, escalations inbox, left message). The line's design: `docs/adr/0001-live-chat-line-in-postgres.md`. How each part is built: `AGENTS.md`. Defects and changes found along the way go in `correction.md`.

Scope: only the update-phase features. Slices 1 to 3 stay as built, apart from the small fixes the new features depend on (per-customer limits, the escalations inbox, chat session renewal).

## Rules

- **The application keeps working at every step.** Each step ships in its own PR into `dev`, merged only on green CI. The agent, the handbook rules, the duplicate guard, the lead approval gate, and the split between chat and staff tokens stay as they are. The existing tests stay green, and each step adds tests for its requirement ids.
- **Live chat sits behind a switch.** `LIVE_CHAT_ENABLED` is off by default. Malatesha turns it on locally and in `dev`. `prod` stays off until he chooses. With it off, the product behaves exactly as today.
- **Schema changes are additive.** New tables and nullable columns, in the same idempotent `SCHEMA_SQL` style. No existing column or case status changes meaning.
- **Postgres holds shared state.** The line, presence, assignment, and limits live in the database, never in process memory (ADR 0001).
- **Talking and approving stay separate.** Specialists take live chats. Leads approve and do not take live chats. A specialist may raise a proposal but never approve it (R4, R22, and `proposed_by`).
- **The agent decides to hand over; the database runs the live chat.** A LangGraph interrupt fits a single approval decision, as today, not a conversation of many messages (ADR 0001).
- Every step records approach changes and defects in `correction.md`.

## What the code showed (2026-10-09)

Checked in the code before planning:

- `case_messages.role` has no check constraint. The chat view sends any non-customer row through `_for_customer`, which swaps the text by decision. A specialist's message must skip that mapping.
- The specialist's desk opens their latest case by owner. Chat cases are owned by `chat@northstar.example`, so a live chat must not change case ownership.
- The request limit is a dict in memory (`CaseStore._requests`). It resets on restart and is not shared across processes.
- The daily model budget (20,000 tokens, 1,000 per handbook turn) is charged to `chat@northstar.example` for every chat customer. All chat customers share about 20 handbook answers a day.
- No query lists escalated cases.
- The chat token lasts 30 minutes (`CHAT_MINUTES`) and the cookie matches. There is no renewal.
- The schema is created at startup by `SCHEMA_SQL`. There is no migration tool.
- CI has no secrets: no model, vector search, judge, or LangSmith keys.

## U0: bounded model calls and graph runs (done, #128)

- Every model call: at most 3 attempts, at most 20 s each, and one retry layer. Calls outside `create_agent` (wording, translation, photo) let the client retry (`max_retries=3`; google-genai counts attempts including the first). The agent's model and fallback make one attempt, and `ModelRetryMiddleware(max_retries=2)` retries.
- Before: `timeout=None` and `max_retries=6`, under the middleware's 3 attempts. One call could make up to 18 requests, each with no time limit.
- Step caps: the router runs with `recursion_limit=10` (it uses 3). The agent subgraph runs with its own `recursion_limit=50`, set on its call so the router's value does not carry over. Measured with a scripted model: a normal agent turn needs 26, and the worst case `run_limit=3` allows needs 43. The installed LangGraph 1.2.14 defaults to 10007.
- The background groundedness judge: `timeout=30`, `max_retries=1`.

## U1: quality within the trace budget (R48)

Why: this month's LangSmith usage was about 3,855 evaluator traces, about 1,165 experiment traces, and 158 app traces. A retry stays inside its trace, so retries were not the cause. Each experiment row adds one trace per evaluator.

- One code evaluator returns several scores (`label_match`, `citation_valid`, `status_correct`, `reply_language`, `photo_verdict`) instead of one evaluator each. LangSmith supports a list of `{"key", "score"}` results from one evaluator.
- `--repetitions 1` while developing. Three repetitions only for the release run on `test`.
- `evaluate(..., upload_results=False)` for local checks (supported in langsmith 0.14.4).
- The router experiment runs only when routing changes.
- Malatesha sets a usage limit in the LangSmith workspace.
- **The release bar runs locally, not in CI.** CI has no keys, and no keys go into GitHub. Before each promotion into `uat`, the release run writes a results file with the commit it ran on and each gate's result. CI on the PR into `uat` checks that the file names the PR's commit and that every gate passed. A promotion cannot skip the bar.
- Each row records its latency and token use. `evals/release_bar.gates()` computes the gates from them.
- **Latency targets:** the English test cases keep the release bar (p95 under 10 s). Spanish turns took about 16 s on a live run, because of two translation calls. They get their own target (p95 under 20 s), tracked in the results file and improved later.
- Later, not now: a second LangSmith account with a fresh monthly allowance for the demo, with a run budget so it is not used up before the interview.

## U2: fair limits and a bounded conversation (R35, R36, R37)

- **Per-customer chat limits:** 10 agent turns per customer per day, and 500 agent turns per day across all chat customers, as a cost ceiling. Both are settings. A specialist's reply in a live chat uses no model and charges nothing.
- **Limits in Postgres:** the request counter and the daily budget move to tables keyed by limit key and day, so they survive a restart and hold across server processes.
- **Turn deadline:** 45 s per turn. Python cannot stop a running thread, so the per-call limits from U0 are the hard bound. Before each optional step (handbook wording, translation), the turn checks the time left and skips the step when time is short. The reply falls back to the cited handbook text, as it already does without a model key.
- **No-progress stop:** after 3 turns in a row that end in `ask_clarification`, `abstain`, or `lookup_failed`, the chat shows a "Talk to a person" button (with live chat on) or "a specialist can follow up" (with it off). The customer decides. `ModelCallLimitMiddleware(thread_limit=...)` is a further cap per conversation.

## U3: escalations inbox (R38)

- A staff list of escalated cases with their handoffs, from the desk and from the chat. Left messages appear here too.
- Leads see every item. Any specialist can pick one up, which assigns it to them so two people do not work it.
- For a chat customer, the specialist's reply goes into that customer's chat. The project sends no email. The chat tells the customer to come back with the same order id and email to read the reply.
- With live chat off, this closes today's gap: "a specialist will follow up" has a place where it happens.

## U4: line, availability, and offers (R42, R43)

Data, new tables only:

```text
specialist_availability  staff_id PK, state ('available' | 'away'), capacity int (default 2), last_seen timestamptz
live_chat_requests
                id, case_id, customer_id, reason ('escalated' | 'requested'), language,
                status ('waiting' | 'offered' | 'active' | 'idle' | 'ended' | 'abandoned' | 'left_message'),
                staff_id, offers int, missed_by uuid[], queued_at, offered_at, offer_expires_at,
                accepted_at, first_reply_at, last_customer_at, last_specialist_at, customer_seen_at,
                ended_at, end_reason
                one open request per case (partial unique index on the open statuses)
case_messages   new role value 'specialist', and a nullable author_staff_id
audit_log       events: live_chat_requested, offered, accepted, declined, expired, ended
```

Routing:

- **Available:** a specialist sets Available or Away on the desk. They count as available only while their desk has checked in within 60 s. Closing the laptop drops them out. Two missed offers in a row set them to Away.
- **Capacity:** 2 live chats per specialist at once, a setting per specialist.
- **Who gets the offer:** the available specialist with the most spare capacity ("Most Available" in Salesforce, "highest spare capacity" in Zendesk). Ties go to whoever was offered work longest ago. A specialist who missed this request is skipped for it.
- **Line order:** escalated before requested, then oldest first.
- **One assignment function**, in one transaction: lock the next waiting request with `SELECT ... FOR UPDATE SKIP LOCKED`, lock the chosen specialist's presence row, count their open live chats against capacity, and set the request to `offered` with a 45 s expiry. With the one-open-request index, two processes cannot give one customer to two people (ADR 0001).
- **When it runs:** a request is created; an offer is accepted, declined, or expires; a live chat ends or goes idle; a specialist changes state. Expired offers are noticed on read: an `offered` row past `offer_expires_at` counts as waiting again. No scheduler is needed at first.
- **Offers:** 45 s to accept. On timeout or decline, the next specialist. After 3 offers, the customer is offered to leave a message, and leads see an alert.
- **A customer who leaves the line:** the customer chat refreshes every 3 s while waiting. If it has not refreshed for 2 minutes, the request is abandoned. A customer who comes back joins at the back.

## U5: talk to a person, the wait estimate, and left messages (R39, R40, R41, R47)

- **Ways in:** a "Talk to a person" control in the chat. The no-progress button from U2. An escalation in the chat joins the line automatically, ahead of requested chats, when a specialist is available and the estimate is under the cap. Otherwise it goes to the escalations inbox with "a specialist will follow up".
- **While waiting:** the agent keeps answering (order status, handbook questions), and a gated action raised while waiting still goes to a lead. The agent stops the moment a specialist accepts. The customer can leave the line at any time.
- **Estimate:** `wait ≈ position × average chat length ÷ available slots`. Position 1 is next. With k customers ahead and every slot busy, the wait is k + 1 chat endings at the combined rate. That is the M/M/c result for first-come-first-served lines, so it is an estimate. Average chat length is the median from accepted to ended over the last 7 days. The chat shows a range, about 0.7× to 1.5×, rounded.
- **Too little history** (fewer than 5 live chats in 7 days): "a few minutes" instead of a number, as Intercom does.
- **Cap:** when the estimate is over 20 minutes, or no specialist is available, the customer is offered to leave a message instead of joining the line. A left message becomes an escalated case in the inbox (U3).
- **Session:** the chat token is renewed while a request or live chat is open, so the customer is not signed out mid-chat. Identity stays order id plus the order's email.
- **Shape kept:** `GET /chat` keeps `{status, messages}`. The place in line and the estimate go in `status`. A specialist's messages carry role `specialist` and the specialist's first name.
- **Later:** the measured wait for each place in line, as Zendesk does (last 10 minutes, then 2 hours, then 7 days). Erlang C is for planning staff, not live estimates, because it assumes one contact per agent.

## U6: the specialist's live chat console (R44, R45, R46)

- New routes only: `POST /presence`, `GET /live`, `POST /live/{id}/accept`, `/decline`, `/messages`, `/resolve`, `/escalate`, and `POST /live/next`. Customer: `POST /chat/live`, `DELETE /chat/live`, `POST /chat/renew`.
- A "Live chats" panel on the desk with offers (accept or decline) and the specialist's live chats, and a page per live chat. The specialist's own desk case does not change.
- **On the live chat page:** the conversation so far (agent turns included), the customer's orders, the history panel, and a "Spanish" label when the customer writes in Spanish. The specialist replies in the customer's language. A person's words are never machine-translated.
- **Replies:** the specialist types them. Each message passes `screen()` before the customer sees it and is audited. A specialist can post only into live chats assigned to them, checked in the query.
- **Money actions:** the specialist raises a refund, cancel, exchange, address change, or warranty claim through the existing `ask` pipeline on that case, as themselves. The proposal goes to the lead's approval list, and the customer sees "Nothing is approved yet". The specialist cannot approve it.
- **The agent is quiet:** while a specialist holds the live chat, `chat_ask` stores the customer's message and skips the agent. No model call, no budget charge.
- **Photos:** still refused in the customer chat, live or not.
- **Quiet customer** (the clock runs only after the specialist's last message): "Are you still there?" at 2 minutes. At 3 minutes the live chat goes idle and the specialist's slot is free for the next request. A returning customer goes back to the same specialist if they have a slot, otherwise to the front of the line, with the conversation kept. Closed at 15 minutes. Zendesk's default for freeing a slot is 10 minutes. 3 is stricter, and it is a setting.
- **Quiet specialist:** a customer waiting more than 2 minutes for a reply is flagged to leads. The live chat is not reassigned automatically.
- **Ending:** the specialist ends a live chat with Resolve (the case is Resolved) or Escalate (the case is Escalated, with a handoff, into the inbox). These are the same outcomes as on the desk.
- **Updates:** the live chat page, the desk panel, and the customer chat refresh every 3 s.

## U7: lead view, metrics, and evals (R49)

- **Lead view:** specialists available, the line's length, the longest wait, the average chat length, and alerts (3 offers reached, quiet specialist).
- **Labeled cases** for the hand-over decisions: "I want a person" and the three-failures offer.
- **LangSmith feedback** `handover_reason` on traced chat turns, to see how often the agent resolves a case without a person.
- **A browser test with three browsers:**
  1. A customer asks for a person.
  2. A specialist accepts the offer and replies.
  3. The customer sees the reply and answers.
  4. The specialist resolves, and the case shows Resolved.

  With axe on each new screen, as the current suite does.

## Later

- Server push instead of page refresh: FastAPI `EventSourceResponse` (in the installed FastAPI 0.142) fed by Postgres `LISTEN/NOTIFY`. Notifications arrive on commit, carry at most 8000 bytes, and are lost when no one listens, so send ids, not message bodies.
- Skill routing: Spanish chats to Spanish-speaking specialists.
- The measured wait for each place in line.
- "Suggest a reply": the agent drafts, the specialist edits and sends.
- Support hours. For now, live chat is offered whenever a specialist is available.
- Photos in live chats.
- A second LangSmith account for the demo.

## Build order

U0 (done) → U1 → U2 → U3 → U4 → U5 → U6 → U7. U1 to U3 fix what is already shipped and work with live chat off. U4 to U7 add live chat behind the switch. Each step is its own PR into `dev`, merged on green CI, with the full test suite passing.

## Tests to add (no live model needed)

- A model that hangs: the turn returns within the deadline, and the next turn works.
- A model that keeps calling the tool stops at three calls inside the step cap (added in #128).
- Three turns without progress: the chat offers a person.
- One customer at their daily limit does not block another. The 500-turn total stops further agent turns. Limits survive a new `CaseStore`.
- An escalated chat appears in the inbox. A specialist picks it up, and their reply reaches the customer's chat.
- Ten customers and two specialists with two slots each: exactly four offered, none twice, and the line drains escalated first, then oldest. The same with many threads at once.
- An expired offer goes to the next specialist. Two missed offers set a specialist to Away. Three offers bring leave-a-message. A desk that has not checked in for 60 s gets no offers.
- With the test clock: a customer who stops refreshing for 2 minutes leaves the line. 3 minutes of customer silence frees the slot. The customer's reply returns to the same specialist. 15 minutes closes the live chat.
- A specialist's proposal in a live chat waits for a lead, and the specialist cannot approve it.
- `GET /chat` keeps `{status, messages}`. A specialist's message is screened and shown as theirs. The agent does not reply while a specialist holds the chat.
- The wait estimate for the worked example: two specialists, two slots each, a 6-minute average. Four chats end about every 6 minutes, so positions 1 and 4 wait about 1.5 and 6 minutes.
- With `LIVE_CHAT_ENABLED` off: no live chat control appears, and every existing chat test passes unchanged.
- The three-browser test from U7.

## Agreed settings

| Setting | Value |
| --- | --- |
| Agent turns per chat customer per day | 10 |
| Agent turns per day, all chat customers | 500 |
| Turn deadline | 45 s |
| Failed turns in a row before offering a person | 3 |
| Live chats per specialist at once | 2 |
| Window to accept an offer | 45 s |
| Offers per request before leave-a-message | 3 |
| Missed offers in a row before Away | 2 |
| Desk check-in for Available | within 60 s |
| Waiting customer gone (no refresh) | 2 min |
| Quiet customer: nudge, slot freed, closed | 2, 3, 15 min |
| Quiet specialist flagged to leads | 2 min |
| Longest estimate before leave-a-message | 20 min |
| Page refresh | 3 s |
| Latency target, English test cases | p95 under 10 s |
| Latency target, Spanish turns | p95 under 20 s |
| Who takes live chats | Specialists only |
| Support hours | Whenever a specialist is available |

## Sources

- LangGraph: [interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts), [GRAPH_RECURSION_LIMIT](https://docs.langchain.com/oss/python/langgraph/errors/GRAPH_RECURSION_LIMIT)
- LangChain: [built-in middleware](https://docs.langchain.com/oss/python/langchain/middleware/built-in), [handoffs](https://docs.langchain.com/oss/python/langchain/multi-agent/handoffs)
- LangSmith: [several scores from one evaluator](https://docs.langchain.com/langsmith/multiple-scores)
- Twilio TaskRouter: [reservations](https://www.twilio.com/docs/taskrouter/api/reservations), [multitasking](https://www.twilio.com/docs/taskrouter/multitasking)
- Salesforce: [QueueRoutingConfig](https://developer.salesforce.com/docs/atlas.en-us.object_reference.meta/api/sforce_api_objects_queueroutingconfig.htm)
- Zendesk: [capacity rules](https://support.zendesk.com/hc/en-us/articles/4776409839770-Creating-capacity-rules-to-balance-agent-workloads), [estimated wait time](https://support.zendesk.com/hc/en-us/articles/8945071149210-Displaying-the-estimated-wait-time-banner-in-messaging-conversations)
- Intercom: [reply time](https://www.intercom.com/help/en/articles/732436-share-your-expected-response-time)
- Queueing: [M/M/c queue](https://en.wikipedia.org/wiki/M/M/c_queue), [Erlang C limits for chat](https://soon.works/blog/erlang-c-multi-channel-limitations)
- PostgreSQL: [SELECT ... SKIP LOCKED](https://www.postgresql.org/docs/current/sql-select.html), [NOTIFY](https://www.postgresql.org/docs/current/sql-notify.html)
- FastAPI: [server-sent events](https://fastapi.tiangolo.com/reference/sse/). Next.js: [router.refresh](https://nextjs.org/docs/app/api-reference/functions/use-router)

## Tasks

- [x] U0: bounded model calls and graph runs (#128)
- [x] U1: quality within the trace budget (#132, #133)
- [x] U2: fair limits and a bounded conversation (#134, #135, #137)
- [x] U3: escalations inbox (#136)
- [x] U4: line, availability, and offers (#138, #139)
- [x] U5: talk to a person, the wait estimate, and left messages (#140, #141)
- [x] U6: the specialist's live chat console (#138, #142, #143)
- [x] U7: lead view, metrics, and evals (#144, #145)

## Built differently

What the build changed against the design above. Every item is tested, and the details are in `correction.md`.

- **Names:**
  - The availability table is `specialist_availability`, because the glossary keeps "agent" for the AI.
  - The setting is `LIVE_CHAT_ENABLED`.
  - What the customer chat suggests (leave a message, talk to a person) is a "follow-up" (`/chat/state` key `follow_up`), so it does not clash with a specialist's offer.
  - The hand-over reason is LangSmith feedback `handover_reason` on traced chat turns, not run metadata, because "three failures" is known only after the turn.
- **Lock order:** the assignment locks the available specialists first, always in the same order, and then claims the request with `SKIP LOCKED`. The opposite order could leave a customer waiting while a specialist who had just become available was free.
- **Request statuses:** waiting, offered, active, idle, ended, refused, abandoned, left, unanswered. Each live chat records an `end_reason` and the customer's `language`.
- **Routing:**
  - Ties go to the specialist offered work longest ago (`last_offered_at`).
  - A decline does not count toward away; only expired offers do.
  - A declined request is never offered back to that specialist.
- **Escalations in the line:**
  - An escalation the line takes keeps its case Open with its handoff until the live chat ends. If it leaves the line without a specialist, it goes to the escalations inbox.
  - While it waits, the agent stays quiet, so it cannot, for example, propose a refund after a chargeback. This is an exception to "the agent keeps answering while waiting", pending Malatesha's decision.
- **Typed requests:** "I want a person" and similar phrases in the customer chat bring the same follow-up as three failed turns.
- **Proposals in a live chat:**
  - A live chat cannot end while its case waits for a lead.
  - The quiet close waits until the lead decides, and records `end_reason = closed_quiet` under the Resolved status.
- **"Take next":** `POST /live/next` lets an available specialist with a free slot take the next request now.
- **Settings:** every default lives in one module (`northstar/defaults.py`) read by both the store and the API settings. Chats per specialist is `LIVE_CHATS_PER_SPECIALIST`.
- **Release bar:**
  - It runs locally and CI checks the committed results file, because CI holds no keys.
  - `TOKEN_CAP` (10,000 per turn) is a first guess, to be set from the first real release run.
  - Spanish turns come from `dev` and count only toward their own p95 and the zero-tolerance gates.
- **Not done here:** splitting the case module (`cases.py` now holds the live chat code too) is a follow-up PR.

