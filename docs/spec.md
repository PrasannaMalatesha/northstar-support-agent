# Spec: Northstar Support Agent, slice 1

Scope: every P0 feature and requirement R1 to R33 in `prd.md`. How each part is built: `AGENTS.md`. Build order: `docs/plans/slice-1-build-phases.md`. Terms follow `CONTEXT.md`. Anything not in `prd.md` is out of scope.

## Problem Statement

Northstar Goods support specialists answer the same handbook questions, look up orders, and decide refunds under time pressure. A general chatbot invents rules and order facts. A refund button with no review moves money before anyone checks it. Leads have no single place to see what is waiting for their decision. Staff can't tell whether a drafted answer is backed by the handbook or made up, and a reviewer of the system can't see why the agent answered, which handbook section it used, which tools it called, or where it still fails.

## Solution

A hosted staff console, with its own login, where a specialist opens a case for a customer, pastes the customer's words, and gets back:
- a draft reply grounded in the Northstar handbook, with section citations and match strength;
- order facts read only from that customer's orders;
- catalog facts read only from catalog rows;
- a proposed action.

Anything that moves money (refund, partial credit) stops as a proposal, and only a lead can approve, edit or reject it. Approval creates exactly one ticket. Abuse and jailbreaks get a fixed safe reply. Questions the handbook doesn't cover are abstained or escalated, never invented. Every turn is traced in LangSmith and scored by a labeled evaluation set. A release that misses the release bar does not deploy.

## User Stories

**Login and access**
1. As a specialist, I want to sign in with my own email and password, so that my work is attributed to me.
2. As a lead, I want to sign in with my own account, so that my approval decisions are recorded under my name.
3. As an admin, I want to create staff accounts with a script, so that there is no public sign-up.
4. As a staff member, I want to paste my password or use a password manager at login, so that signing in doesn't rely on memory.
5. As a staff member, I want repeated wrong passwords to lock the login briefly, so that my account resists guessing.
6. As a staff member, I want my session to expire and logout to end it, so that an unattended laptop is not a risk.
7. As the project owner, I want every API call without a valid session refused, so that only signed-in staff reach the agent.
8. As the project owner, I want no model, database or backend token visible in the browser, so that secrets cannot leak from the console.
9. As an auditor, I want every login success, failure, logout and approval decision recorded, so that access and decisions can be reviewed.
10. As a staff member, I want the console to say "waking the server" when the free host is asleep, so that I don't mistake a cold start for an error.

**Opening a case**
11. As a specialist, I want to find a customer by email or phone in common formats, so that I bind the right customer to the case.
12. As a specialist, I want to open a case without a customer when none is found, so that I can still answer handbook and catalog questions.
13. As a specialist, I want an unbound case to reply "pick a customer first" to any order question, so that no order is read without a customer.
14. As a specialist, I want to type or paste the customer's message and an optional order id, so that the agent works from the customer's own words.
15. As a specialist, I want the agent never to choose or create the customer, so that identity stays my decision.

**Handbook answers**
16. As a specialist, I want handbook questions on any handbook topic answered from the handbook, so that the reply matches company rules.
17. As a specialist, I want every factual claim to cite a handbook section id, so that I can check it.
18. As a specialist, I want to see whether each citation was a strong or weak match, so that I know how much to trust the draft.
19. As a specialist, I want a weak match or an uncovered question to abstain and name what to ask next, so that the agent never invents a rule.
20. As a specialist, I want a follow-up such as "what about shipping?" to stay on the same case, so that I don't repeat the context.

**Order facts**
21. As a specialist, I want an order id owned by the case customer to return status, order lines, purchase date and prior refunds, so that I can answer accurately.
22. As a specialist, I want an order id owned by someone else to return "not found for this customer" with no details, so that customer data stays private.
23. As a specialist, I want an unknown order id reported as unknown, so that no order is invented.
24. As a specialist, I want the agent never to invent tracking events, so that I don't promise something the record doesn't show.

**Catalog answers**
25. As a specialist, I want questions about what Northstar sells answered only from catalog rows (name, category, price, sizes or variants, in stock yes or no, final sale), so that product facts are reliable.
26. As a specialist, I want an unknown item, or a field the row doesn't have, to abstain, so that the agent doesn't describe products from general knowledge.
27. As a specialist, I want stock shown as yes or no only, so that I don't promise a quantity or a hold.

**Refunds and approval**
28. As a specialist, I want the agent to propose approve, partial credit or deny, with an amount and the handbook rule used, so that the lead can decide quickly.
29. As a specialist, I want a refund request without an order id or reason to ask for the missing fact, so that no proposal depends on a guess.
30. As a specialist, I want an already-refunded line to be refused a second refund, citing the record, so that money is not paid twice.
31. As a specialist, I want the proposed amount never to exceed the order and always to follow the handbook rule, so that proposals are safe to approve.
32. As a specialist, I want the case status to show "Waiting for approval" while a proposal is pending, so that I know it's blocked on a lead.
33. As a specialist, I want no approve control on my screen, so that I can't approve my own proposal.
34. As a lead, I want a waiting for approval list with the action, amount, order id, age and stale flag, so that I can find every pending decision.
35. As a lead, I want to open a case desk from a list row, so that I decide with full context.
36. As a lead, I want approve, edit amount and reject as three separate, well-spaced controls, so that I don't click the wrong one.
37. As a lead, I want reject to ask for a short reason, so that the specialist knows why.
38. As a lead, I want approval to confirm with the ticket id, so that I know it was recorded.
39. As a lead, I want a double click or a replayed approval to return the same ticket, so that duplicates are impossible.
40. As a lead, I want proposals older than 24 hours flagged as stale but still waiting, so that nothing is decided automatically.
41. As a lead, I want to be unable to approve a proposal I raised myself, so that two people always check money movement.
42. As a specialist, I want a waiting approval to survive an API restart on the same case, so that closing a laptop or a redeploy loses nothing.

**Safety and escalation**
43. As a specialist, I want slurs and jailbreaks to get a fixed safe reply and no tool call, so that the agent can't be manipulated.
44. As a specialist, I want full payment numbers removed and email or phone masked in the draft, so that customer data is minimized.
45. As a specialist, I want legal, chargeback and ambiguous policy-conflict cases escalated with a short handoff (what was asked, what the handbook says, what is missing), so that the right person picks them up.
46. As a specialist, I want an escalated case marked Escalated, so that its status is clear.
47. As a specialist, I want to see only a draft that passed the safety check, so that I never see text that is later withdrawn.

**Customer history**
48. As a specialist, I want a read-only history panel showing the customer's 5 most recent cases (id, status, outcome, refunded lines), so that I see what happened before.
49. As a specialist, I want the agent to use that same record to stop a duplicate refund, so that history protects against double payment.
50. As a specialist, I want history never to set an amount or override the handbook, so that past cases don't become policy.
51. As a specialist, I want the history panel empty on an unbound case, so that no customer data shows without a customer.

**Finishing a case**
52. As a specialist, I want to edit the draft before sending it through my usual channel, with both the agent's draft and my final text saved, so that edits are traceable.
53. As a specialist, I want to mark a case Resolved, so that it's closed.
54. As a specialist, I want Resolved and Escalated cases to accept no new messages or proposals, so that closed cases stay closed.
55. As a specialist, I want a follow-up from the same customer to open a new case that shows up in their history, so that the record stays complete.

**Experience and accessibility**
56. As a specialist, I want the desk to show the agent's steps as they happen (classifying, reading the handbook, looking up the order), with the first step within 400 ms, so that I know it's working.
57. As a specialist, I want the decision, evidence, context and process laid out in that order, with one accent color reserved for waiting for approval, so that the important thing is obvious.
58. As a keyboard or screen-reader user, I want every control reachable by keyboard, with visible focus and announced step updates, so that I can work the whole case without a mouse.
59. As a staff member, I want empty and error states that tell me the next step inline, so that I never need a manual.
60. As a staff member, I want a clear message when I hit a request or daily model budget limit, with the case not lost, so that I know what happened and can continue later.

**Quality program**
61. As the project owner, I want a labeled set of about 40 cases split 10 train_judge, 15 dev and 15 test, so that quality is measured on held-out data.
62. As the project owner, I want code checks for action, route, path, citations and the approval gate, plus judges for correctness and groundedness, so that both facts and wording are scored.
63. As the project owner, I want judges calibrated against human labels on train_judge before they gate test, so that judge scores are trustworthy.
64. As the project owner, I want v0 and v1 run on the same cases with repetitions and a pairwise comparison, so that improvements are shown, not claimed.
65. As the project owner, I want a release that misses any release-bar number not to deploy, so that regressions never reach prod.
66. As the project owner, I want live traffic sampled by online evaluators and failures added back to the labeled set, so that the set tracks reality.
67. As a reviewer, I want every turn traced in LangSmith with its tools, retrieved sections, rerank scores and decision, so that I can investigate any failure.

## Implementation Decisions

**Architecture**
- Next.js console in front, FastAPI API behind it, a LangGraph agent, Postgres, Pinecone, and LangSmith. The browser talks only to Next.js server route handlers (backend for frontend). Only FastAPI holds model, database, and vector keys.
- Ports and adapters: domain rules have no I/O, ports define what the agent needs, and adapters are the only code that imports SDKs. A new store, model, or reranker is a new adapter, not a graph change.
- Single sources: one settings object holds all limits and token caps, one versioned prompt registry is tagged on traces, and one section id registry is read by ingest, the citation check, and the dataset validator.

**Deep modules.** Small interfaces with the complexity hidden behind them. Graph nodes and API routes call only these.

| Module | Interface | What it hides |
| --- | --- | --- |
| `identity` | login, refresh, logout, current staff from a token | argon2id hashing, token signing, refresh rotation, lockout, audit |
| `cases` | open case, bind customer, resolve, escalate, history for a customer | status rules, read-only enforcement, saving draft and final text |
| `handbook` | answer a question, returning a cited answer or an abstain | embedding, Pinecone top-20, FlashRank top-4, score threshold, citation registry check |
| `catalog` | look up items, returning rows or an abstain | Postgres catalog query, the row-fields-only rule |
| `orders` | get an order for the case, returning an order view or "not found for this customer" | customer scoping from case state, the unbound-case refusal, refunded lines |
| `approvals` | propose, list pending, decide (lead, proposal, decision) | LangGraph interrupt and resume, the proposer-cannot-approve rule, idempotent tickets, stale flag, audit |
| `guard` | screen input, screen output | deterministic blocks, PII middleware, moderation, fixed safe replies |
| `usage` | check and charge (staff, tokens) | per-user request limits, daily token quota, the limit message |
| `evals` | evaluator registry, run a split | code graders, openevals judges, rate limiter, LangSmith experiments |

**Agent**
- A LangGraph StateGraph with an `intent_classifier` node that routes by `Command(goto)` to two `create_agent` subgraphs: `support_agent` (handbook, catalog and order questions) and `refund_agent` (refund and partial credit). Both end in `compile_followup`, which writes the user-visible reply.
- Middleware:
  - PII redaction and masking
  - human-in-the-loop on the ticket tool only
  - tool and model call limits
  - model retry with backoff
  - model fallback
  - tool retry and a "lookup failed" error reply that never fills in facts
  - summarization above the message cap
- Structured output is a validated Pydantic model through the tool strategy, never a raw schema dict. Fields: intent, action (answer, approve_refund, partial_credit, deny, escalate, ask_clarification), refund amount in cents, policy citations, rationale, customer reply, awaiting approval, ticket id.
- Tools:
  - `retrieve_policy`: the only retrieval tool.
  - `lookup_catalog`: a Postgres read, not vector search.
  - `lookup_order`: the customer id always comes from case state, never from the model.
  - `create_refund_ticket`: runs only after an approved resume.
- Guardrails run before the router and after `compile_followup`. A deterministic block ends the turn before any model call.

**Retrieval**
- Pinecone similarity search returns the top 20, with section id metadata.
- The FlashRank reranker (`ms-marco-MiniLM-L-12-v2`) keeps the top 4 above a score threshold. If nothing passes the threshold, the agent abstains.
- The threshold is tuned on dev only. FlashRank memory is measured on the 512 MB free host first.
- Retrieve and rerank are separate traced child runs, and the rerank score is shown to staff as strong or weak.
- The handbook is version `northstar-policy-v2`, frozen, ingested per environment into its own namespace, and stamped on every run.

**Memory and persistence**
- One case is one LangGraph thread, persisted by the Postgres checkpointer. That covers the conversation and the approval pause.
- A cases table maps a customer to their cases with status and outcome.
- The history record is built from app tables when a case opens, never from transcripts, and it has its own token cap. The history panel reads the same record.

**Data (app tables, conceptually)**
- Staff accounts (role specialist or lead), login attempts and lockout, refresh tokens (hashed), audit log
- Customers, orders and order lines with fulfillment and refund state, catalog items
- Cases (customer, thread, status, draft text, final text)
- Proposals (case, proposer, action, amount, rule, created time)
- Tickets (unique on thread and proposal, approver, decision time)
- Daily token usage per staff member
- All seed data is synthetic.

**API contract (behavioral)**
- Auth: login, refresh, logout. The API returns a 15-minute access token and a rotating refresh token. Auth.js keeps both in an encrypted, httpOnly cookie, and the browser sees only name and role.
- Customers: look up by email or phone.
- Cases: open (bound or unbound); post a message (streams step events, then one final checked draft); save final text; resolve; read the case with its history record.
- Approvals: list pending (lead only, with age and stale flag); decide (lead only, not the proposer, approve, edit amount, or reject with a reason). Approving is idempotent.
- Every route checks the session and loads the role from the database. Roles are never trusted from the client. Request bodies are validated with size and length caps. CORS is limited to the environment's console origin. State-changing console routes check the request Origin header.
- Rate limits: login lockout at 5 failures in 15 minutes (stored in Postgres); per-user and per-chat-customer request limits in Postgres (`daily_limits`, update phase #134); a daily token quota in Postgres; a model-call rate limiter in process.

**Console**
- Three screens: login, case desk, and the waiting for approval list.
- The visual hierarchy and the UX law table from the PRD Experience section are binding.
- WCAG 2.2 AA.
- Step progress streams; the draft arrives once, after the output check.

**Environments and delivery**
- Environments are local, dev, uat and prod, each with its own Vercel deployment, Render service, Neon branch, Pinecone namespace and LangSmith project.
- Branches are `main`, `dev`, `uat` and `prod`. Feature branches merge into `dev` by PR, then promote `dev` to `uat` to `prod`. After a release, `prod` is merged back into `main`.
- CI gates:
  - into `dev`: lint (including jsx-a11y), unit tests, graph tests with mocks, code graders, a 5-row smoke eval, `pip-audit` and `npm audit`;
  - into `uat`: the full test-split experiment and the release bar, plus an axe scan;
  - into `prod`: reviewer approval.

## Testing Decisions

- A good test drives the system from outside, the way a real caller does, and asserts only observable behavior: HTTP status and body, streamed events, database rows that a user would see (tickets, case status, audit), and trace contents. It never asserts private functions, prompt text, or call order inside a module.
- **Seam 1: the FastAPI HTTP API.** These are the same calls the Next.js server makes. Fake adapters replace the model, Pinecone, the reranker and the clock. A real Postgres runs in a container or on a Neon branch. Every requirement except the eval-measured ones and R32 is accepted here. Examples:
  - login lockout after five failures;
  - a specialist decide call is refused;
  - the proposer can't approve;
  - a double approve returns one ticket;
  - an order owned by another customer returns not found;
  - an unbound case refuses order questions;
  - a resolved case rejects a message;
  - a waiting approval survives an app restart;
  - the token quota message;
  - no secret appears in any response;
  - the clock fake advances 24 hours and the stale flag shows.
- **Seam 2: the LangGraph graph invoke,** used by LangSmith experiments:
  - final-response judges (correctness, groundedness, helpfulness);
  - code graders (action, amount, citation validity and requirement, retrieval recall, hit at 4, MRR, hallucination rate, no invented order);
  - the router checked in isolation;
  - trajectory subsequence and extra step count;
  - tool-argument matching.

  Human approval in an example is supplied as the expected decision, so the interrupt is resumed, never skipped.
- **Seam 3: Playwright with axe on the three screens,** for R32 only. Includes a keyboard-only walkthrough of login, a case turn, and a lead decision.
- Domain modules are not unit-tested directly. One exception: pure domain rules with no I/O (amount math, return window checks) may get table tests, because the API seam can't cover all the boundary dates cheaply.
- Prior art: none in this repo yet. The patterns come from the LangSmith complex-agent evaluation guide (final response, single step, trajectory), the LangSmith pytest integration, and the openevals prebuilt judges.
- Release bar, measured on test (from `prd.md`):
  - action correct at least 80%;
  - zero tickets without approval;
  - zero invalid citations;
  - every abstain row abstains;
  - p95 turn latency under 10 seconds, excluding approval wait;
  - no token cap exceeded.

## Out of Scope

- Everything marked P1 and P2 in `prd.md`:
  - cancellation, address change, exchange proposals, and warranty claim drafts;
  - the lost-shipment workflow and the open-ticket check;
  - the approval queue that decides from the list, and the full handoff packet;
  - stored specialist corrections and the handbook gaps list;
  - customer preference memory;
  - customer-facing chat, photo intake, other languages, real payments and carrier APIs, SSO.
- A customer login or storefront. Charging cards or moving real money. Web search as a knowledge source. The agent writing or changing handbook sections. LangSmith Agent Server (requires a paid plan).
- Any screen, control, or behavior not listed in `prd.md`.

## Further Notes

- Build order is the eight phases in `docs/plans/slice-1-build-phases.md`. Phase 0 writes handbook v2 and builds no code.
- Before each technical decision, open the matching LangChain, LangGraph or LangSmith doc and cite it in `architecture.md` or `correction.md`.
- Keep `AGENTS.md`, `architecture.md`, `explanation.md` and `correction.md` updated in the same change as each decision.
- Free-tier limits that shaped the design are recorded in `AGENTS.md`: Render sleep and 512 MB, the Neon branch per environment, the Pinecone rerank quota, and Vercel Hobby preview branches.
- Branch protection rules are set up in Phase 1, once the CI checks they require exist.
