# Update phase: production readiness and live human support

Status: planned, not started, except U0 (done in #128). Grill this plan before opening tickets.

Source of scope: `prd.md`, update phase, R34 to R49. How each part is built: `AGENTS.md`. Defects and changes found along the way go in `correction.md`.

## Rules

- **Nothing that works today breaks.** The agent, the handbook rules, the duplicate guard, the lead approval gate, and the split between chat and staff tokens stay as they are. The existing tests stay green.
- **Live human chat sits behind a switch.** `LIVE_AGENTS_ENABLED` off means the product behaves exactly as today.
- **Schema changes are additive.** New tables and nullable columns, in the same idempotent `SCHEMA_SQL` style. No existing column or case status changes meaning.
- **Postgres holds shared state.** The line, presence, assignment, and limits live in the database, never in process memory.
- **Talking and approving stay separate.** A specialist may talk to a customer and raise a proposal. Only a lead approves (R4, R22, and `proposed_by`).
- **The agent decides to hand over; the database runs the human conversation.** A LangGraph interrupt waits for one resume value and re-runs its node on resume. That fits a single approval decision, as today. A conversation of many messages over minutes belongs in a table.
- **Every phase:** a `feature/*` branch, a PR into `dev`, merged on green CI, tests for each requirement id, and an entry in `correction.md` when an approach changes.

## What the code showed (2026-10-09)

Checked in the code before planning:

- `case_messages.role` has no check constraint. The chat view sends any non-customer row through `_for_customer`, which swaps the text by decision. A person's message must skip that mapping.
- The specialist's desk opens their latest case by owner. Chat cases are owned by `chat@northstar.example`, so live chat must not change case ownership.
- The request limit is a dict in memory (`CaseStore._requests`). It resets on restart and is not shared across processes.
- The daily model budget is charged to `chat@northstar.example` for every chat customer, so all chat customers share one budget.
- No query lists escalated cases.
- The chat token lasts 30 minutes (`CHAT_MINUTES`) and the cookie matches. There is no renewal.
- The schema is created at startup by `SCHEMA_SQL`. There is no migration tool.

## U0: bounded model calls and graph runs (done, #128)

- Every model call: at most 3 attempts, at most 20 s each, one retry layer. Calls outside `create_agent` (wording, translation, photo) let the client retry (`max_retries=3`; google-genai counts attempts including the first). The agent's model and fallback make one attempt; `ModelRetryMiddleware(max_retries=2)` retries.
- Before: `timeout=None` and `max_retries=6`, stacked under the middleware's 3 attempts: up to 18 requests for one call, each with no time limit.
- Step caps: the router runs with `recursion_limit=10` (it uses 3). The agent subgraph runs with its own `recursion_limit=50`, set on its call so the router's value does not carry over. Measured with a scripted model: a normal agent turn needs 26 and the worst case `run_limit=3` allows needs 43, because each middleware hook is its own step. The installed LangGraph 1.2.14 defaults to 10007.
- The background groundedness judge: `timeout=30`, `max_retries=1`.

## U1: quality within the trace budget (R48)

Why: this month's LangSmith usage was about 3,855 evaluator traces, about 1,165 experiment traces, and 158 app traces. A retry stays inside its trace, so retries were not the cause. Each experiment row adds one trace per evaluator.

- One code evaluator that returns several scores (`label_match`, `citation_valid`, `status_correct`, `reply_language`, `photo_verdict`) instead of one evaluator each. LangSmith supports a list of `{"key", "score"}` results from one evaluator.
- `--repetitions 1` while developing. Three repetitions only for the release run on `test`.
- `evaluate(..., upload_results=False)` for local checks (supported in langsmith 0.14.4).
- The router experiment runs only when routing changes.
- A usage limit set in the LangSmith workspace.
- Record each row's latency and token use, feed them to `evals/release_bar.gates()`, and run the release bar in CI on PRs into `uat` (AGENTS.md already says it should).
- Spanish turns took about 16 s on a live run, against p95 under 10 s. Measure it on the new gate, then make translation faster or skip it under the turn deadline.
- Later, not now: a second LangSmith account with a fresh monthly allowance for the demo. Plan a run budget so it is not used up before the interview.

## U2: fair limits and a bounded conversation (R35, R36, R37)

- **Per-customer budget:** charge the daily model budget by `("chat", customer_id)`, the same key the request limit already uses. A specialist reply in a live chat uses no model and charges nothing.
- **Limits in Postgres:** move the request counter from memory to a table keyed by limit key and day.
- **Turn deadline:** about 45 s per turn. Python cannot stop a running thread, so the per-call limits from U0 are the hard bound. Before each optional step (handbook wording, translation), check the time left and skip it when short. The reply falls back to the cited handbook text, as it already does without a model key.
- **No-progress stop:** after 3 turns in a row that end in `ask_clarification`, `abstain`, or `lookup_failed`, the agent stops and offers a person (or opens a `review` handoff when live chat is on). `ModelCallLimitMiddleware(thread_limit=...)` is a further cap per conversation.

## U3: escalations inbox (R38)

- A staff list of escalated cases with their handoff packets, from the desk and the chat. Leads see all. Specialists see the ones they can take.
- With live chat off, this closes today's gap: "a specialist will follow up" has a place where it happens.

## U4: line, presence, and assignment (R42, R43)

Data, new tables only:

```text
agent_presence  staff_id PK, state ('available' | 'away' | 'offline'), capacity int, last_seen timestamptz
handoffs        id, case_id, customer_id, reason ('requested' | 'escalated' | 'review'), priority, language,
                status ('queued' | 'offered' | 'active' | 'idle' | 'ended' | 'abandoned' | 'expired'),
                staff_id, offers int, queued_at, offered_at, offer_expires_at, accepted_at,
                first_reply_at, last_customer_at, last_agent_at, ended_at, end_reason
                one open handoff per case (partial unique index on open statuses)
case_messages   new role value 'agent', and a nullable author_staff_id
audit_log       events: handoff_requested, offered, accepted, declined, expired, ended
```

Routing, as Zendesk, Salesforce, and Twilio do it:

- **Capacity:** each available specialist has a number of chat slots. A specialist counts as online when `state = 'available'` and `last_seen` is within 60 s. The desk's refresh updates `last_seen`.
- **Who gets the chat:** the specialist with the most spare capacity ("Most Available" in Salesforce, "highest spare capacity" in Zendesk). Ties go to whoever was offered work longest ago.
- **Line order:** priority (escalated, then requested, then review), then oldest first.
- **One assignment function**, in one transaction: lock the next queued handoff with `SELECT ... FOR UPDATE SKIP LOCKED`, lock the chosen specialist's presence row, count their open chats against capacity, and set the handoff to `offered` with an expiry. Postgres documents `SKIP LOCKED` for queue-like tables with many consumers. With the one-open-handoff index, two processes cannot give one customer to two people.
- **When it runs:** a handoff is created; an offer is accepted, declined, or expires; a chat ends or goes idle; a specialist changes state. Expired offers are noticed on read (an `offered` row past `offer_expires_at` is treated as queued), so no scheduler is needed at first.
- **Offers:** a 45 s window to accept. On timeout or decline, the next specialist. After 3 offers, the customer gets the leave-a-message option and the lead is alerted. After 2 missed offers in a row, the specialist is set to away.

## U5: talk to a person and the wait estimate (R39, R40, R41, R47)

- A "Talk to a person" control in the chat. The agent also opens a handoff on an escalation or a no-progress stop.
- **Estimate:** `wait ≈ position × average chat length ÷ available slots`. Position 1 is next. With k customers ahead and every slot busy, the wait is k + 1 chat endings at the combined rate. That is the M/M/c result for first-come-first-served lines, so it is an estimate. Average chat length is the median from accepted to ended over the last 7 days. Show a range, about 0.7× to 1.5×, rounded.
- **Too little history** (fewer than 5 chats in 7 days): say "a few minutes" instead of a number, as Intercom does.
- **Cap:** over 20 minutes, or no specialist online, offer to leave a message. It becomes a case in the escalations inbox.
- **Later:** use the measured wait for each place in line, as Zendesk does (last 10 minutes, then 2 hours, then 7 days). Erlang C is for planning staff, not for live estimates, because it assumes one contact per agent.
- **Chat token renewal** while a handoff is open, so a customer is not signed out mid-chat.
- `GET /chat` keeps its `{status, messages}` shape. The place in line and the estimate go in `status`. A person's messages carry role `agent` and the specialist's first name.

## U6: the specialist's live chat console (R44, R45, R46)

- New routes only: `POST /presence`, `GET /live`, `POST /live/{id}/accept`, `/decline`, `/messages`, `/end`, and `POST /live/next`. Customer: `POST /chat/handoff`, `DELETE /chat/handoff`, `POST /chat/renew`.
- A "Live chats" panel on the desk and a page per chat. The specialist's own desk case does not change.
- A specialist can post only into chats assigned to them, checked in the query. Their messages pass `screen()` before the customer sees them and are audited.
- While a person holds the chat, `chat_ask` stores the customer's message and skips the agent: no model call, no budget charge.
- **Gated actions in a live chat:** the specialist runs the existing `ask` pipeline on that case as themselves. The proposal goes to the lead's queue. The customer sees "Nothing is approved yet".
- **Quiet customer** (the clock runs only after the specialist's last message): "Are you still there?" at 2 minutes. At 3 minutes the chat goes idle and the slot is free for the next customer. A returning customer goes back to the same specialist if they have a slot, or to the front of the line, with the conversation kept. Closed at 15 minutes. Zendesk's default for freeing a slot is 10 minutes. 3 is stricter, and it is a setting.
- **Quiet specialist:** a customer waiting more than 2 minutes for a reply is flagged on the lead's view. It is not reassigned automatically.

## U7: lead view, metrics, and evals (R49)

- Lead view: specialists online, line length, longest wait, average chat length.
- Labeled cases for the hand-over decision ("I want a person", repeated failures).
- LangSmith metadata `handoff_reason` on root runs, to see how often the agent resolves a case without a person.

## Later

- Server push instead of page refresh: FastAPI `EventSourceResponse` (in the installed FastAPI 0.142) fed by Postgres `LISTEN/NOTIFY`. Notifications arrive on commit, carry at most 8000 bytes, and are lost if no one listens, so send ids, not message bodies.
- Skill routing: Spanish chats to Spanish-speaking specialists.
- Measured wait per place in line.

## Build order

U0 (done) → U1 → U2 → U3 → U4 → U5 → U6 → U7. U1 to U3 fix what is already shipped and work with live chat off. U4 to U7 add live chat behind the switch.

## Tests to add (no live model needed)

- A model that hangs: the turn returns within the deadline and the next turn works.
- A model that keeps calling the tool stops at three calls inside the step cap (added in #128).
- Three turns without progress: the agent offers a person.
- One customer at their budget does not block another. Limits survive a new `CaseStore`.
- Ten customers, two specialists with three slots each: exactly six offered, none twice, the line drains in order. The same with many threads at once.
- An expired offer moves to the next specialist. Two missed offers set a specialist to away. Three offers bring leave-a-message.
- With the test clock: 3 minutes of customer silence frees the slot; the customer's reply returns to the same specialist; 15 minutes closes the chat.
- A specialist's proposal in a live chat waits for a lead, and the specialist cannot approve it.
- `GET /chat` keeps `{status, messages}`; a person's message is screened and shown as theirs.
- The wait estimate for the worked example: two specialists, three slots each, a 6-minute average, so positions 1 and 4 wait about 1 and 4 minutes.

## Settings to agree

See `prd.md`, Open points: chats per specialist, the accept window, offers before leave-a-message, missed offers before away, the quiet-customer times, the wait cap, the no-progress count, support hours, and whether leads take live chats.

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
- [ ] U1: quality within the trace budget
- [ ] U2: fair limits and a bounded conversation
- [ ] U3: escalations inbox
- [ ] U4: line, presence, and assignment
- [ ] U5: talk to a person and the wait estimate
- [ ] U6: the specialist's live chat console
- [ ] U7: lead view, metrics, and evals
