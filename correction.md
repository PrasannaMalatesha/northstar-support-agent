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
