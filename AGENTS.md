# Northstar Support Agent

Canonical project contract. When this file and a chat disagree, follow this file. Official LangChain, LangGraph, and LangSmith docs win over memory when an API detail is in doubt.

Before a technical agent decision (graph shape, tools, memory, retrieval, guardrails, evaluators, tracing), open the matching doc and cite the URL in `architecture.md` or `correction.md`. If the doc and this file disagree, update this file to match the doc, then record the change in `correction.md`.

Product: **Northstar Support Agent** for fictional DTC brand Northstar Goods. A standalone support assistant a human can trust. General company questions use RAG. Refunds and credits require human approval before any ticket is created.

Owner: Malatesha. Take-home bar: evaluation instincts, LangSmith fluency, honest failures, and a crisp investigation when handed a new failure case.

## Authorship

Every commit, PR, issue, and release in this repository is authored by Malatesha (`PrasannaMalatesha`) only. No `Co-authored-by` trailers, "Made with" footers, or tool credits in commits, PRs, docs, or code.

## Build gate

Implement only when Malatesha says to build. Until then, update this file when decisions change.

During implementation, export a presentation image from the Northstar architecture canvas. Write `diagrams/northstar-architecture.png` (and a JPEG copy if the renderer supports it) into this repo. The canvas is the layout source. The image is what gets shown in a walkthrough. Update the image in the same change if the architecture boxes change.

## Core requirements

Readability, maintainability, and modularity are required.

- A feature lives in one module. A change to that feature stays in that module and its tests.
- Callers depend on a small interface. A new retrieval engine, model, or database is a new adapter behind that interface. It does not edit the caller.
- A small change must not force edits across the codebase. If it does, the boundary is wrong. Fix the boundary before adding the next feature.
- A name says what the module does. A reader follows one feature without reading unrelated modules.
- A rule has one source. The handbook, the section registry, and the eval cases are not copied into a second place.

## Stack

- Next.js for the support console (chat and refund approval)
- Python FastAPI for the HTTP API
- Python for the LangGraph agent, LangChain tools, RAG, guardrails, and evals
- LangSmith traces, datasets, experiments, feedback, dashboards, alerts, online evaluators
- Offline evals: `langsmith.evaluate` / `aevaluate` and `@pytest.mark.langsmith`
- Trajectory: `trajectory_subsequence` from the complex-agent guide, plus `agentevals` when tool arguments must match
- Model: `gemini-3-flash-preview` for the agent (`GOOGLE_API_KEY`, `AGENT_MODEL`). Judge model: `JUDGE_MODEL`, default `nvidia/nemotron-3-ultra-550b-a55b:free` on OpenRouter (`OPENROUTER_API_KEY`). The judge is not the agent model. ([Google GenAI](https://docs.langchain.com/oss/python/integrations/chat/google_generative_ai), [OpenRouter](https://openrouter.ai/docs/quickstart))
- Vector database: Pinecone, via `langchain-pinecone` `PineconeVectorStore` ([Pinecone integration](https://docs.langchain.com/oss/python/integrations/vectorstores/pinecone)). Policy chunks only. Not chat history
- Rerank after Pinecone top-k: the `flashrank` package `Ranker` with model `ms-marco-MiniLM-L-12-v2` (ONNX on CPU, no Torch), called from the `Reranker` adapter. Pass the model name; the old wrapper's default is `ms-marco-MultiBERT-L-12`, which is the wrong model. Keep at most 4 chunks at or above `RETRIEVAL_SCORE_TAU`. Same reranker in local, CI, dev, uat, and prod. `langchain-community` was sunset on 2026-05-22, so do not import `FlashrankRerank` ([sunset](https://github.com/langchain-ai/langchain-community/issues/674), [FlashRank](https://github.com/PrithivirajDamodaran/FlashRank)). A replacement is a new adapter: hosted `PineconeRerank` ([Pinecone rerank](https://docs.langchain.com/oss/python/integrations/retrievers/pinecone_rerank)) stays behind the port and is not the default
- PostgreSQL for everything that must survive a restart:
  - Short-term memory: `PostgresSaver` / `AsyncPostgresSaver` keyed by `thread_id` ([checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers)). This is the conversation and the HITL pause
  - Long-term memory: `PostgresStore` keyed by namespace and key, shared across threads ([add memory](https://docs.langchain.com/oss/python/langgraph/add-memory), [stores](https://docs.langchain.com/oss/python/langgraph/stores))
  - App tables: refund tickets and approval audit
- Local Postgres matches production. `InMemorySaver` is not the production checkpointer; the checkpointer docs use it for experimentation and it dies on process restart ([checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers))
- Postgres host: Neon free plan, one project, one Neon branch per environment (`dev`, `uat`, `prod`). Render free Postgres is not used: one per workspace and deleted 30 days after creation ([Render free](https://render.com/docs/free), [Neon limits](https://neon.com/faqs/free-plan-limits-and-quotas))
- Share: Vercel (Next.js) + Render (FastAPI), one Render service per environment. LangSmith Developer for traces and evals

LangSmith Cloud Agent Server requires Plus. Document it as a paid upgrade. The demo API is FastAPI, not Agent Server.

## Required files

These stay next to this file. A decision is not done until the matching file is updated.

| File | What it holds |
| --- | --- |
| `prd.md` | Product requirements. What the product is, who it is for, and which features exist. Technical design is not decided here. |
| `AGENTS.md` | Contract. Agents follow this when building |
| `architecture.md` | Components, data stores, request path, and the diagrams used to explain the system |
| `explanation.md` | What was decided, in what order, and why. Written for a person |
| `correction.md` | Approach changes, bugs, and the debug steps that fixed them |
| `CONTEXT.md` | Glossary of domain terms |
| `docs/spec.md` | Implementation spec for slice 1 |
| `docs/plans/` | Phase 0 handbook plan and the slice 1 build phases |

`trd.md` is the technical requirements document. Do not write it until Malatesha asks. It will be derived from `prd.md` and this file.

## Sources of truth

| Source | Owns |
| --- | --- |
| `data/policy/*.md` | Company policy. Stable `section_id`s are the only citable policy facts. |
| `data/policy/SECTION_IDS.md` | Registry of every section ID |
| `data/orders.json` | Seed order state loaded into Postgres. Runtime order reads go to Postgres, not a fresh invention |
| This file | Product, architecture, eval, security, and deploy decisions |
| LangSmith docs | How tracing, datasets, experiments, and online evals work |

Corpus version is stamped on every run as `policy_corpus_version`. The frozen handbook is `northstar-policy-v2`.

The handbook is written by this project and then frozen. The topics follow common marketplace practice. The sentences are original Northstar text. Amazon, Flipkart, and other retailers are not copied. The running agent does not add sections.

Slice 1 is a specialist console. The specialist supplies the case. The agent checks the customer row and that customer's orders in Postgres before it states a purchase fact. The customer does not log in.

Slice 1 token budget fails closed. Retrieve 20, pass at most 4 reranked chunks into the answer prompt. Keep at most the last 6 case messages. One judge call per experiment row. The judge sees the question, the gold answer or the cited chunks, and the draft, not the tool logs. Over budget, the case abstains or the eval row fails. LangSmith token and cost fields are the record. Extra tool calls are `extra_step_count`.

### Policy docs to author

| File | Section IDs | Covers |
| --- | --- | --- |
| `company-overview.md` | `CO-ABOUT`, `CO-CATEGORIES`, `CO-SCOPE` | Who Northstar is, the four categories, what support does not do |
| `returns-and-refunds.md` | `REF-WINDOW`, `REF-CATEGORY`, `REF-CONDITION`, `REF-ELIGIBILITY`, `REF-PARTIAL`, `REF-DENY`, `REF-DAMAGED`, `REF-WRONG-ITEM`, `REF-MISSING-ITEM`, `REF-FINAL-SALE`, `REF-METHOD`, `REF-TIMING`, `REF-SHIP-COST`, `REF-GIFT`, `REF-HOLIDAY`, `REF-INSPECTION` | Window, category lengths, condition, eligibility, partial credit, denials, damage, wrong and missing items, final sale, method, timing, label fee, gifts, holiday, inspection |
| `exchanges.md` | `EXC-ELIGIBILITY`, `EXC-STOCK`, `EXC-LIMIT`, `EXC-PROCESS`, `EXC-DIFFERENT-ITEM`, `REP-REPLACEMENT` | Size or color swaps, stock, one exchange, a different item, replacement of a damaged item |
| `shipping-and-delivery.md` | `SHIP-REGIONS`, `SHIP-OPTIONS`, `SHIP-SLA`, `SHIP-DELAY`, `SHIP-LOST`, `SHIP-ADDRESS`, `SHIP-SPLIT`, `SHIP-DNR`, `SHIP-REFUSED` | Where Northstar ships, prices, SLAs, delays, lost packages, address changes, split shipments, delivered-not-received, refusals |
| `warranty.md` | `WAR-COVERAGE`, `WAR-EXCLUSIONS`, `WAR-CLAIM`, `WAR-REMEDY`, `WAR-RECALL` | Coverage after the return window, exclusions, claims, remedy, recall |
| `order-changes.md` | `ORD-CANCEL`, `ORD-MODIFY`, `ORD-TRACK`, `ORD-PARTIAL-CANCEL` | Cancel, modify, tracking, cancel one line |
| `payments-and-pricing.md` | `PAY-METHODS`, `PAY-CHARGE-TIMING`, `PAY-TAX`, `PAY-PRICE-ADJUST`, `PAY-PRICE-ERROR`, `PAY-DUPLICATE` | Methods, when the card is charged, tax, price drops, pricing errors, duplicate holds |
| `promotions-and-gift-cards.md` | `PROMO-CODES`, `PROMO-RETURNS`, `PROMO-THRESHOLD`, `GC-TERMS`, `GC-LOST`, `STORE-CREDIT` | Codes, discounted refunds, free-shipping threshold, gift cards, store credit |
| `support-escalation.md` | `ESC-WHEN`, `ESC-ABUSE`, `ESC-LEGAL`, `ESC-FRAUD` | Escalation, abuse, legal / chargeback, fraud |
| `privacy-and-pii.md` | `PII-MINIMIZE`, `PII-SHARE`, `PII-PAYMENT`, `PII-DELETE` | What support may say, card numbers, deletion |
| `faq-general.md` | `FAQ-HOURS`, `FAQ-CONTACT`, `FAQ-ACCOUNT`, `FAQ-PASSWORD`, `FAQ-EMAILS`, `FAQ-SIZING` | Hours, contact, account, passwords, marketing email, sizes |

Gold labels cite real section IDs only. A citation that is not in the registry is a failed example, not a valid answer.

## What the agent does

| Intent | Behavior | Trust boundary |
| --- | --- | --- |
| Policy, FAQ, shipping, warranty | Retrieve the handbook, rerank, pass at most 4 chunks, then answer with citations | Answer only when a section supports the claim. Otherwise abstain. |
| Catalog | Read catalog rows | Name, category, price, sizes or variants, in stock yes/no, final-sale flag only. Unknown item or a field not on the row: abstain. |
| Order status | `lookup_order` scoped to the case customer | The specialist binds the case to one customer by email or phone lookup. `lookup_order` takes `customer_id` from case state, never from the model. An order owned by someone else returns "not found for this customer" with no details |
| Refund, return, credit | Propose action, then human approve / edit / reject | `create_refund_ticket` runs only after an approved resume |
| Slur, abuse, jailbreak | Guardrail redirect | Safe template. No engagement with hate. No policy bypass. |
| Ambiguous or out of corpus | `ask_clarification` or `escalate` | Abstain. The corpus wins over the user. |

Structured output always includes: `intent`, `action` (`answer` | `approve_refund` | `partial_credit` | `deny` | `escalate` | `ask_clarification`), `refund_amount_cents` when relevant, `policy_citations`, `rationale`, `customer_reply`, `awaiting_approval`, `ticket_id`.

Tools: `retrieve_policy`, `lookup_catalog`, `lookup_order`, `create_refund_ticket` (HITL-gated). `lookup_catalog` reads Postgres catalog rows. It is not a vector search. `retrieve_policy` is the only RAG tool, and it reads the frozen handbook.

## Graph

Adopt the shape from the official customer-support eval guide ([Evaluate a complex agent](https://docs.langchain.com/langsmith/evaluate-complex-agent)), not the Chinook music database.

```
intent_classifier
  -> refund_agent        (refund subgraph)
  -> support_agent       (policy and order questions)
both -> compile_followup -> END
```

`intent_classifier` returns `Command(goto=...)` with `refund_agent` or `support_agent`. The official example uses `question_answering_agent` because that subgraph queries a SQL catalog. Ours answers from the policy corpus and `orders.json`, so the node is `support_agent`.

`compile_followup` writes the user-visible string on state key `followup`. Final-response eval reads that key, matching the docs (`result["followup"]`).

Refund subgraph, in order when the data is present: `retrieve_policy`, `lookup_order`, propose, `interrupt` for approval, then `create_refund_ticket`. If order id or identity is missing, `gather_info` asks for it and does not invent it. The official Chinook refund node writes a refund immediately, with `config={"env": "test"}` to mock the write. Northstar does not copy that. Money movement stays behind human approval even in tests. An eval example that expects a ticket includes `hitl_decision: approve` so the target function resumes the interrupt. An example that should stop at the proposal ends at `awaiting_approval`.

Support subgraph: `retrieve_policy`, rerank, score gate, cited answer or abstain. `lookup_order` only when the question is about an order.

Guardrails run before `intent_classifier` and again after `compile_followup`.

## Policy-first path

1. Retrieve policy. Call `lookup_order` when an order id is present.
2. Rerank. If the best score is below `RETRIEVAL_SCORE_TAU`, abstain.
3. Cite section IDs.
4. Propose the action from those chunks and tool JSON only.
5. Interrupt for human approval before creating a refund ticket.

Generation context is the reranked chunks plus tool JSON. If the answer is not in that context, say so and ask a clarifying question.

Retrieval shape: embed the query, Pinecone similarity top-20 with `section_id` metadata (`PineconeVectorStore`, namespace per environment), then the `Reranker` adapter calls `flashrank.Ranker(model_name="ms-marco-MiniLM-L-12-v2")` and keeps at most 4 passages whose score is at least `RETRIEVAL_SCORE_TAU`. Expose that score on the trace as `relevance_score`. Abstain when nothing passes the threshold. Trace child runs `retrieve` and `rerank`. Tune `RETRIEVAL_SCORE_TAU` on `dev` only, never on `test`. Phase 2 measures FlashRank memory on the Render free instance (512 MB) first and records the number in `correction.md`. Embedding dimension must match the Pinecone index. The official Pinecone notebook uses dimension 1536 with a matching OpenAI embedding and `ServerlessSpec(cloud="aws", region="us-east-1")`; set both from env and do not mix models. Starter indexes are us-east-1 only ([Pinecone pricing](https://www.pinecone.io/pricing/)).

## Grounding

The agent states a policy rule only when a retrieved chunk contains it. Order ids, amounts, dates, and ticket ids come from tools. Steps in the trace are real tool calls and a real interrupt, not a narrated path.

Evaluators score faithfulness over fluency. A fluent answer with a missing or invented citation fails. Judge prompts see the retrieved context and the answer, not the open web. Score groundedness 0 when any claim is unsupported by that context.

Deterministic checks, all CI-relevant:

- `citation_valid` — every citation is in the section registry
- `citation_required` — policy and refund proposals cite at least one section (pure order lookup may omit policy citations)
- `retrieval_used` — `retrieve_policy` ran before a policy claim
- `retrieval_score_gate` — weak retrieval abstains
- `no_invented_order` — order facts match `lookup_order`
- Groundedness and hallucination-trap failures block the PR

Golden slices include a correct citation, an out-of-corpus abstain, a user claim that conflicts with policy, a trap that invites a wrong window (for example “14 days” when the doc says 30), weak retrieval, and a refund that skipped retrieval.

## Guardrails

Guardrails wrap every phase: what enters the agent, which tools may run, and what the user sees. LangChain middleware is the implementation. Evaluators prove each layer held. A blocked request ends before the main model call when a deterministic input check fails, so that request spends no agent tokens.

Two mechanisms, used together:

| Mechanism | When | Northstar use |
| --- | --- | --- |
| Deterministic | Regex, keyword, schema, allowlist. No model call. | Slur lexicon, jailbreak patterns, PII patterns, tool allowlist, amount bounds, citation registry |
| Model-based | A small model judges semantic intent | Output safety, educational-vs-malicious nuance, groundedness of the final reply |

Deterministic checks run first. A model judge never replaces a hard block.

### Stack order

1. **Before-agent input filter.** Banned abuse and jailbreak patterns, auth, rate limit, max length. Violation returns a fixed safe reply and jumps to end.
2. **PII middleware** on user input, tool arguments, and final output. Built-in types are `email`, `credit_card`, `ip`, `mac_address`, and `url` ([built-in middleware](https://docs.langchain.com/oss/python/langchain/middleware/built-in)). Email: `redact`. Card numbers: `mask` via `credit_card`. Phone is not a built-in type; use a custom detector and `redact`. API keys and secrets: a custom detector with `block`. Hash only when a stable pseudonym is required for logs.
3. **Human-in-the-loop** on `create_refund_ticket` only. Checkpointer holds the thread. Resume with `Command(resume=...)`: `approve` runs the tool, `edit` runs the revised args, `reject` returns feedback and creates no ticket.
4. **After-agent output check.** OpenAI moderation plus a lightweight safety classifier. Unsafe or uncited policy claims are replaced with a safe fallback or an abstain. The user never sees the raw unsafe draft.

Retrieval score gate sits with the tools: weak retrieval abstains before a confident answer. Tool args are validated (`order_id` format, amount within order total and policy cap).

Staff log in with real accounts (see "Frontend, auth, and security"). SSO is a later upgrade. Log the approval decision, the approver's user id, and `thread_id` on the ticket and in trace metadata.

Console streaming: stream graph step progress (node and tool names) only. The draft is sent once, after the after-agent output check. Never stream draft tokens that the check could withdraw.

Labeled set, slice 1: about 40 examples, splits `train_judge` 10 / `dev` 15 / `test` 15. The release bar runs on `test`. An example never changes split after first use.

Roles: two demo logins, `specialist` and `lead`. Only `lead` may send the resume for approve, edit, or reject, and the API checks this, not only the UI. The proposer cannot approve their own proposal. A proposal waiting more than 24 hours is shown as stale and is never auto-approved or auto-rejected (PRD R22, R23).

### What this does not change

The take-home still requires a working agent, at least one tool, RAG over the policy corpus, a golden dataset, deterministic graders, an LLM judge, traces, a v0-to-v1 experiment, honest failures, and a production-eval story. Guardrails are the safety shell around that agent. They are not a substitute for policy grounding or the four eval layers.

## Evaluation

Source for the three offline strategies: [Evaluate a complex agent](https://docs.langchain.com/langsmith/evaluate-complex-agent) and [Evaluation approaches](https://docs.langchain.com/langsmith/evaluation-approaches). Every experiment is `client.aevaluate(target, data=dataset_name, evaluators=[...], experiment_prefix=..., num_repetitions=1, max_concurrency=4)` unless a pytest gate needs a tighter assert.

An experiment has three parts, as that guide states: a golden dataset (inputs plus reference outputs), a target function (the graph or one node), and evaluators. The target runs on the inputs. Evaluators score outputs against reference outputs. LangSmith stores the trace, the score, and run stats (latency, tokens, errors).

Agents are hard to eval because the path is chosen by the model, not hard-coded. A correct final answer can still hide extra tool calls. Those extra calls cost latency and tokens. Ship a prompt, model, or graph change only after the three strategies below, plus the safety and production checks, do not regress.

The video names two trajectory helpers, `evaluate_extra_steps` and `evaluate_unmatched_steps`. Those names are not in the current docs page. The published scorer is `trajectory_subsequence`. Use that. Add `extra_step_count` ourselves because subsequence match does not penalize extra steps: its loop advances through the actual path and only checks that expected steps appear in order.

### Strategy 1 — final response

Dataset: `Northstar Support: E2E`. Each example has `inputs.question` and `outputs.response` (and `outputs.trajectory` so the same rows can feed strategy 3).

Target `run_graph` invokes the graph and returns `{"response": result["followup"], "trajectory": ...}`.

Evaluator `final_answer_correct` is the docs teacher-quiz judge. System prompt grades only factual accuracy against the ground-truth response, rejects conflicting statements, and allows extra detail when that detail is still accurate relative to the ground truth. Structured output is `reasoning` plus `is_correct` (bool). Judge model is `JUDGE_MODEL`, default `nvidia/nemotron-3-ultra-550b-a55b:free` via OpenRouter, temperature 0. The docs sample calls `init_chat_model(..., temperature=0).with_structured_output(Grade, method="json_schema", strict=True)`. Do not change the rubric to reward style. Do not point `JUDGE_MODEL` at the agent model.

This judge does not check citations. The docs rubric can mark a paraphrase correct with no section id. Northstar also runs code checks `citation_valid` and `citation_required` on the same experiment. An uncited policy claim fails even when `is_correct` is true. A separate groundedness judge scores 0 when a claim is not in the retrieved chunks. The quiz judge sees question, ground truth, and student response. The groundedness judge sees retrieved chunks and the student response, not the open web.

### Strategy 2 — single step (intent router)

Dataset: `Northstar Support: Intent Classifier`. Inputs are `messages` (one turn or a short history). Reference output is `route`: `refund_agent` or `support_agent`.

Target does not run the full graph. It runs the node alone, as the docs do:

`command = await graph.nodes["intent_classifier"].ainvoke(inputs)` then `{"route": command.goto}`.

Evaluator `correct` is `outputs["route"] == reference_outputs["route"]`. Include a multi-turn row where a refund turn is followed by a policy question, so the router uses the latest user message. That pattern is in the official intent dataset.

### Strategy 3 — trajectory

Same E2E dataset. Reference `trajectory` is an ordered list of node and tool names, for example `["refund_agent", "retrieve_policy", "lookup_order"]` or `["support_agent", "retrieve_policy"]`.

Record the path with `graph.astream(..., subgraphs=True, stream_mode="debug")`, as the docs specify. On `chunk["type"] == "task"`, append `chunk["payload"]["name"]`. When the payload name is `tools`, also append each tool call name. Docs: [streaming subgraphs](https://docs.langchain.com/oss/python/langgraph/streaming).

`trajectory_subsequence(outputs, reference_outputs)` returns the fraction of expected steps found in order. If the reference is longer than the actual path, the docs implementation returns `False`. Otherwise it walks both lists and returns `i / len(reference)`. Extra steps do not lower this score.

`extra_step_count` is Northstar's efficiency check: how many actual steps are not in the reference. CI fails a refund case that calls `create_refund_ticket` when the reference stopped at the interrupt. CI does not require a perfect subsequence of 1.0 on compound questions. The official write-up shows compound questions causing extra course-correction (their example called `lookup_album` before the needed track lookup). We keep one compound policy question in the set and report the subsequence score honestly instead of forcing 1.0.

`agentevals` `strict` / `superset` / `subset` remain for cases where tool arguments must match (`tool_args_match_mode`). Subsequence match checks names and order, not arguments.

### How the three strategies sit on the four layers

| Official strategy | Northstar layer | Grader |
| --- | --- | --- |
| Final response | Layer 1 task outcome | LLM judge `is_correct`, plus citation and groundedness code checks |
| Single-step route | Layer 2, one node | Code equality on `route` |
| Trajectory subsequence and extra steps | Layer 2 full path | Code. Partial credit is the subsequence ratio |
| HITL, allowlist, PII, moderation | Layer 3 | Code, plus a safety-tone judge |
| Latency, tokens, cost, errors on the experiment | Layer 4 | LangSmith run stats, not an LLM |

Reference-based graders run offline. Reference-free groundedness, reply quality, and safety tone also run online. Human review calibrates the quiz judge and the groundedness judge on `train_judge` before those scores gate `test`.

### Layer 1 — task outcome

Did the job finish correctly?

| Key | Grader | Offline | Online |
| --- | --- | --- | --- |
| `action_correct`, `intent_correct`, `amount_correct`, `task_completed` | Code | yes | no, except schema and error-free online |
| `answer_correctness` | LLM judge, reference-based | yes | no |
| `policy_groundedness`, `reply_quality` | LLM judge | yes | yes |
| `customer_satisfaction` | Human | calibration set | sampled |

### RAG evaluators

The four from [Evaluate a RAG application](https://docs.langchain.com/langsmith/evaluate-rag-tutorial), built with `openevals` `create_llm_as_judge` ([openevals](https://docs.langchain.com/langsmith/openevals)). Where a gold label exists, code replaces the judge.

| Key | Compares | Grader | Offline | Online |
| --- | --- | --- | --- | --- |
| `answer_correctness` | Draft vs reference answer | Judge, `CORRECTNESS_PROMPT` | yes | no |
| `policy_groundedness` | Draft vs reranked chunks | Judge, `RAG_GROUNDEDNESS_PROMPT` (takes `context` and `outputs`, not `inputs`) | yes | sampled |
| `reply_quality` | Draft vs question | Judge, `RAG_HELPFULNESS_PROMPT` | yes | sampled |
| `context_recall`, `context_precision`, `retrieval_hit_at_4`, `retrieval_mrr` | Reranked section ids vs gold `expected_sections` | Code | yes | no |
| `retrieval_relevance` | Chunks vs question | Judge, `RAG_RETRIEVAL_RELEVANCE_PROMPT` | no | sampled |

Judges run at temperature 0, one call per row per key, with only the prompt variables listed. Calibration: label `train_judge` by hand, run the judge, record agreement in `results/judge_calibration.md`, add disagreements as `few_shot_examples` or edit the prompt, and only then let the judge gate `test`.

### Layer 2 — trajectory

Strategy 3 above is the path score: `trajectory_subsequence` for coverage, `extra_step_count` for waste, and the intent-classifier experiment for the router alone.

`agentevals` adds argument checks the subsequence scorer does not do:

- `strict` when order and tool args are the contract (policy retrieve, then lookup, then propose, then interrupt)
- `superset` when required tools must appear and extras are allowed
- `subset` when an extra tool is a failure (a FAQ must not call `create_refund_ticket`)
- `unordered` when the tool set matters and order does not
- `tool_args_match_mode` for `order_id` and amounts

`trajectory_quality` is the LLM trajectory judge (`TRAJECTORY_ACCURACY_PROMPT`, with reference when a gold path exists). Use it when a name list is too brittle. Disputed paths go to a human and then into the golden set.

Docs: [trajectory evals](https://docs.langchain.com/langsmith/trajectory-evals).

### Layer 3 — safety and permissions

| Key | Grader |
| --- | --- |
| `hitl_required_respected`, `tool_allowlist_respected`, `amount_in_bounds`, `refusal_on_slur`, `moderation_pass`, `pii_redacted`, `citation_valid`, `retrieval_abstain` | Code |
| `safety_tone`, `permission_escalation` | LLM judge |
| `jailbreak_resistance` | Code and LLM judge |
| Nuanced policy conflicts | Human |

CI has zero tolerance for HITL bypass and allowlist violations.

### Layer 4 — production metrics

Latency p50/p99, time to first token, tokens, cost, step count, error rate. Tag every root run with `agent_version`, `intent`, `slice`, `env`, `deployment_sha`. Metadata includes `step_count`, `tools_called`, `hitl_pending`, `policy_corpus_version`.

Offline: summary checks against the previous experiment. Online: LangSmith dashboards and alerts on latency, cost, errors, and feedback score.

### Where graders run

| Phase | What runs |
| --- | --- |
| Offline experiment | All four layers on the golden dataset |
| CI on PR into `uat` (smoke subset on PR into `dev`) | The PRD release bar: `action_correct` at least 80%; zero tickets without approval; zero invalid citations; every abstain row abstains (outside handbook, unknown catalog item, missing field, order not owned); p95 turn latency under 10 s excluding approval wait; no token cap exceeded. Also: groundedness at threshold, refund trajectories include retrieve and lookup when an order id exists, zero allowlist failures |
| Online | Reference-free groundedness, reply quality, trajectory quality (sampled), safety code checks, dashboards and alerts |
| Human loop | Calibrate judges on `train_judge`, then promote failures into the dataset |

Dataset splits: `train_judge` (few-shot calibration only), `dev`, `test`. Slices: happy path, out of window, damaged, missing order id, already refunded, abuse, partial vs full, ambiguous escalate, policy conflict, jailbreak, out of corpus.

Calibrate LLM judges on human labels before trusting `test` or online scores. Record agreement in `results/judge_calibration.md`.

Online evaluators are reference-free, filtered to root runs, sampled for cost. Low groundedness or reply quality goes to an annotation queue. Schema or safety failures are candidates for the golden dataset. A separate automation rule can alert after the feedback key exists.

Feedback loop: live trace, online score, human label, dataset version, offline experiment, ship only when `test` does not regress.

## Agent build and middleware

The router is a LangGraph `StateGraph` with an `intent_classifier` node and `Command(goto=...)`. `support_agent` and `refund_agent` are each a `create_agent` subgraph, so LangChain's built-in middleware applies ([built-in middleware](https://docs.langchain.com/oss/python/langchain/middleware/built-in), [create_agent](https://reference.langchain.com/python/langchain/agents/create_agent)).

| Middleware | Setting | Problem it covers |
| --- | --- | --- |
| `PIIMiddleware` | `email` redacted, `credit_card` masked, phone via a custom detector and redacted, secrets via a custom detector and blocked | Data leakage |
| `HumanInTheLoopMiddleware` | `interrupt_on` for `create_refund_ticket` only, `allowed_decisions` `approve`, `edit`, `reject`. Requires a checkpointer | Excessive agency, permissions |
| `ToolCallLimitMiddleware` | `run_limit` per tool, `thread_limit` overall | Tool misuse, unbounded usage |
| `ModelCallLimitMiddleware` | per run and per thread | Unbounded usage, loops |
| `ModelRetryMiddleware` | exponential backoff on 429 and 5xx | Rate limits, provider failures |
| `ModelFallbackMiddleware` | second model | Dependency outage |
| `ToolRetryMiddleware`, `ToolErrorMiddleware` | retry transient errors, then a "lookup failed" message. `ToolErrorMiddleware` requires `langchain>=1.3.14`. Place retry inner and `on_failure="error"` so the error middleware sees the exception | Failure recovery. Never fill in facts |
| `SummarizationMiddleware` | trigger above the message cap | Context overflow |

Structured output: `response_format=ToolStrategy(schema=<Pydantic model>, handle_errors=True)`. Never a raw JSON-schema dict: the docs warn that dict schemas are not validated, so `handle_errors` cannot retry ([structured output](https://docs.langchain.com/oss/python/langchain/structured-output)).

Ticket idempotency: unique key on `(thread_id, proposal_id)`. A second approve, a double click, or a replayed resume returns the existing ticket.

## Customer history

- A case is one thread. The `cases` table maps `customer_id` to `thread_id`, status, and outcome. The checkpointer holds the case transcript.
- `PostgresStore` namespace `("customers", customer_id, "prefs")` holds stated preferences only ([stores](https://docs.langchain.com/oss/python/langgraph/stores)).
- At case start the agent receives a short history record built from app tables: past case ids, status, outcome, open or completed tickets, and refunded lines. Preferences join in slice 2 (PRD P1). It never receives past transcripts. The history record has its own token cap.
- History is context, not policy. It can stop a second refund. It cannot set an amount.

## Eval metric catalog

| Key | Grader | Offline | Online | Gate |
| --- | --- | --- | --- | --- |
| `action_correct`, `amount_correct`, `intent_correct` | Code | yes | no | yes |
| `answer_correctness` | Judge `CORRECTNESS_PROMPT` | yes | no | yes |
| `policy_groundedness` (faithfulness) | Judge `RAG_GROUNDEDNESS_PROMPT` | yes | sampled | yes |
| `reply_quality` (relevance) | Judge `RAG_HELPFULNESS_PROMPT` | yes | sampled | report |
| `answer_similarity` | openevals `create_embedding_similarity_evaluator` | yes | no | diagnostic only |
| `context_recall`, `retrieval_hit_at_4` | Code vs gold `expected_sections` | yes | no | yes |
| `context_precision`, `retrieval_mrr` | Code vs gold `expected_sections` | yes | no | report |
| `retrieval_relevance` | Judge `RAG_RETRIEVAL_RELEVANCE_PROMPT` | no | sampled | report |
| `hallucination_rate` | Summary evaluator: share of rows ungrounded, citing a missing section, or inventing an order | yes | dashboard | invented ids must be 0 |
| `trajectory_subsequence`, `extra_step_count`, tool-arg match | Code (agentevals) | yes | sampled | yes |
| `pairwise_preference` | `evaluate_comparative(..., randomize_order=True)` | v0 vs v1, model swaps | no | report |
| Variance | `num_repetitions=3` on `test` | yes | no | report |

Regression: pin the current release experiment as the LangSmith baseline ([analyze an experiment](https://docs.langchain.com/langsmith/analyze-an-experiment)). CI fails when a gate key drops below the release bar or below the baseline by more than the run-to-run variance measured with `num_repetitions`.

Judge scaling:
- Code graders run first. A row that already failed a hard code check skips its judge calls.
- One judge call per row per key, at temperature 0.
- Rate limiting: `InMemoryRateLimiter` on the judge model plus `aevaluate(max_concurrency=4)` ([rate limits](https://docs.langchain.com/langsmith/handle-model-rate-limiting)). The limiter is per process, so CI runs one eval process.

Online sampling: code checks on 100% of runs. Judges on a 10% random sample plus every run that abstained, escalated, or was edited by a specialist.

Drift:
- Weekly, re-run the judges on `train_judge` and compare agreement with the human labels. A drop means judge drift.
- Dashboards track online score trends and the abstain rate per `policy_corpus_version`. A rise means production or knowledge drift.
- Human review: low online scores and specialist edits go to an annotation queue, then into the golden set under a new dataset version.

## Code structure (SOLID, DRY)

The core requirements above are the rule. This is where the modules go.

- `domain/`: pure types and rules (amount math, window checks). No I/O.
- `ports/`: `PolicyRetriever`, `Reranker`, `OrderRepository`, `CatalogRepository`, `TicketRepository`, `CaseRepository`, `CustomerMemory`, `Judge`.
- `adapters/`: Pinecone, FlashRank, Postgres, OpenAI. The only place SDKs are imported.
- `graph/`: router, subgraphs, and middleware wiring. Nodes depend on ports and get adapters by injection.
- `api/`: FastAPI routes, role checks, rate limits.
- `evals/`: one evaluator registry used by offline experiments and online rules.
- Single sources:
  - `config.py` (pydantic-settings) for settings and token caps
  - `prompts/` registry, versioned and tagged on traces
  - `SECTION_IDS.md` registry, read by ingest, `citation_valid`, and the dataset validator

Rule: a new vector store, reranker, model, or database is a new adapter, not an edit to graph code.

## Frontend, auth, and security

Frontend: plain Next.js (App Router). Three screens: login, case desk (with the read-only customer history panel, PRD R33), and the lead's waiting for approval list (PRD R28). No other UI framework is required. Browser code never calls FastAPI and never holds a backend token. Next.js server route handlers are the only gateway (backend for frontend).

Auth flow ([Auth.js credentials](https://authjs.dev/getting-started/authentication/credentials), [third-party backends](https://authjs.dev/guides/integrating-third-party-backends)):
1. A staff member submits email and password to Auth.js `Credentials` in Next.js.
2. `authorize` posts them to FastAPI `/auth/login`.
3. FastAPI checks the `staff_users` row (argon2id hash), the lockout state, and the role. It returns a short-lived signed access token (15 minutes) and a refresh token. Refresh tokens are stored hashed, rotate on every use, and are revoked on logout.
4. Auth.js keeps the tokens inside its encrypted, httpOnly session cookie (`session.strategy = "jwt"`). The `session` callback exposes only the user name and role to the browser, never the tokens.
5. Next.js route handlers call FastAPI server to server with `Authorization: Bearer <access token>`.
6. FastAPI verifies the signature, issuer, audience, and expiry on every request, then loads the role from `staff_users`. It never trusts a role sent by the client.

Accounts: no public sign-up. An admin script seeds staff in each environment. Roles are `specialist` and `lead`. Disabling an account revokes its refresh tokens.

Security baseline:
- HTTPS only. Cookies are `httpOnly`, `Secure`, `SameSite=Lax`.
- State-changing route handlers check the `Origin` header (CSRF).
- CORS on FastAPI allows only that environment's Next.js origin. The intended caller is the Next.js server.
- Security headers in `next.config`: CSP, HSTS, `X-Content-Type-Options`, `Referrer-Policy`, `frame-ancestors 'none'`.
- Secrets live only in server environment variables. Nothing secret uses the `NEXT_PUBLIC_` prefix.
- Pydantic validation on every body, a maximum body size, and a maximum message length.
- Role checks on every FastAPI route (PRD R22). Order lookups use the case customer from case state (PRD R14).
- Audit log in Postgres: login success and failure, logout, approve, edit, reject, account changes.
- CI runs Dependabot, `pip-audit`, and `npm audit`. A high-severity finding blocks the PR into `uat`.
- Traces get the same PII middleware output as the model. Raw payment numbers never reach LangSmith.

Rate limiting:

| Layer | Limit | Storage |
| --- | --- | --- |
| Login | Per IP and per email. Lockout after 5 failures in 15 minutes | Postgres (survives restarts) |
| API requests | Per user and per IP, stricter on `/cases/*/messages` | slowapi in memory, one instance per environment ([slowapi](https://github.com/laurentS/slowapi)) |
| LLM token quota | Daily cap per staff user. Over the cap, the case says the quota is reached | Postgres, read from LangSmith or model usage fields |
| Model calls | `InMemoryRateLimiter`, `ModelRetryMiddleware` | In process |

If an environment scales past one instance, request limits move to a shared store. Note that slowapi's Redis path is synchronous and blocks the event loop ([issue #130](https://github.com/laurentS/slowapi/issues/130)), so that move needs its own decision.

Free-host behavior: a Render free service sleeps when idle and takes about a minute to wake ([Render free](https://render.com/docs/free)). The UI shows a "waking the server" state and retries. It does not show an error.

## UI and accessibility standard

The visual hierarchy and the UX law table live in `prd.md` (Experience). Build to them; do not add screens or controls that are not listed there.

Accessibility target: WCAG 2.2 AA (PRD R32, [what is new in 2.2](https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/)).
- Semantic HTML. Every control has a visible label or an accessible name.
- Visible focus on every control, never fully hidden by sticky content (2.4.11).
- Contrast at least 4.5:1 for text and 3:1 for UI parts and focus rings. The palette tokens are checked once and reused.
- Pointer targets at least 24 by 24 CSS pixels (2.5.8). Approve and reject are spaced apart.
- Login allows paste and password managers (3.3.8). No CAPTCHA.
- Streamed steps use a polite live region. The draft arrives as one announced update.
- Every action works by keyboard alone.

Checks: `eslint-plugin-jsx-a11y` rules (bundled in `eslint-config-next`) on every PR. An automated axe scan of the three screens in Playwright on the PR into `uat`. Confirm the current package docs at Phase 1 before pinning versions.

## Local and cloud

One codebase. One LangSmith tracing project per environment, set by `LANGSMITH_PROJECT`: `northstar-local`, `northstar-dev`, `northstar-uat`, `northstar-prod`. Datasets are shared across environments. Every run and experiment is tagged `env` and `deployment_sha`. The same evaluators apply everywhere.

| Env | Git branch | Web (Vercel) | API (Render) | Postgres (Neon) | Pinecone namespace |
| --- | --- | --- | --- | --- | --- |
| local | any | `next dev` | `uvicorn` | Docker Postgres or a Neon dev branch | `handbook-dev` |
| dev | `dev` | Preview branch with its own domain | Service tracking `dev` | Branch `dev` | `handbook-dev` |
| uat | `uat` | Preview branch with its own domain | Service tracking `uat` | Branch `uat` | `handbook-uat` |
| prod | `prod` | Production branch set to `prod` | Service tracking `prod` | Branch `prod` | `handbook-prod` |

Vercel Hobby supports a persistent staging-style preview branch with its own domain and branch-scoped variables; named custom environments need Pro ([Vercel environments](https://vercel.com/docs/deployments/environments)). Each Render service tracks exactly one branch. Free Render services spin down when idle and share 750 instance hours per workspace per month ([Render free](https://render.com/docs/free)).

## Branching and promotion

```
main  (mirror of what is live; no direct commits)
 ├── dev   ← feature/* by PR
 ├── uat   ← dev by PR
 └── prod  ← uat by PR, then prod is merged back into main
```

Repository: [PrasannaMalatesha/northstar-support-agent](https://github.com/PrasannaMalatesha/northstar-support-agent) (public).

`dev`, `uat`, and `prod` are created from `main`. Work happens on `feature/*` cut from `dev`. Promotion is always by PR, in one direction. Hotfix: `hotfix/*` from `prod`, PR into `prod`, then merged down into `uat` and `dev`. Branch protection on `dev`, `uat`, `prod`, and `main`; free GitHub branch protection needs a public repo.

A finished change is not done until it is committed and pushed to that feature branch on GitHub. If a pull request into `dev` is not already open, open one. When that pull request's checks pass, merge it into `dev`. Do not leave it open for Malatesha to merge. Do not leave completed code only on the local machine. Do not commit secrets. Do not push straight to `main`, `uat`, or `prod`.

## CI and deploy

| PR into | Gate |
| --- | --- |
| `dev` | Lint, unit tests with no LLM (including "every golden citation exists in the registry"), graph checks with mocks, code graders, a 5-row smoke eval |
| `uat` | Full offline experiment on `test` via `evaluate()` and pytest LangSmith marks. The PRD release bar must pass |
| `prod` | The same commit already passed the `uat` gate, plus approval from a reviewer |
| `main` | Fast-forward from `prod` only |

A merge into an environment branch deploys that environment (Vercel and Render auto-deploy on the tracked branch). The handbook ingest runs per environment into its own Pinecone namespace, stamped with `policy_corpus_version`.

Cache model HTTP with `LANGSMITH_TEST_CACHE`. Secrets stay in the server environment. Tracing: `LANGSMITH_TRACING=true`, which also sets `LANGCHAIN_TRACING_V2`. Local project: `northstar-local`.

## v0 then v1

v0 is a naive prompt that can pick the wrong action on edges. v1 is policy-first: mandatory lookup when an order id is present, interrupt before a ticket, abstain on weak retrieval, PII-light replies, escalate on abuse or ambiguity. Run the same dataset on both versions and commit before/after summaries under `results/`.

## Interview failure playbook

When given a new failure:

1. Open the trace. Read tool calls, retrieved chunks, rerank scores, and the structured decision.
2. Classify: retrieval miss, wrong tool or args, policy misread, schema, judge disagreement, HITL skip, or out of distribution.
3. Add a minimal golden example whose expected action and citations match the policy docs.
4. Add a code check when the failure is deterministic. Extend judge few-shots when the rubric drifted.
5. Re-run that example, then the `test` split.
6. Fix the layer that failed: corpus, retrieval gate, tool contract, prompt, or HITL — not a vaguer prompt.

## Layout

```
AGENTS.md  prd.md  architecture.md  explanation.md  correction.md  CONTEXT.md
README.md  Makefile  render.yaml  .github/workflows/
apps/web/                 Next.js console (BFF route handlers, three screens)
apps/api/                 FastAPI routes, auth, rate limits
packages/agent/           domain/ ports/ adapters/ graph/ prompts/ config.py
evals/                    evaluator registry, datasets, experiment runners
data/policy/  data/seed/  (customers, orders, catalog, staff)
docs/spec.md  docs/plans/
diagrams/                 architecture canvas and exported images
results/                  before/after, judge calibration
```

This layout follows `docs/plans/slice-1-build-phases.md`. Deep modules (`identity`, `cases`, `handbook`, `catalog`, `orders`, `approvals`, `guard`, `usage`, `evals`) live under `packages/agent` and are described in `docs/spec.md`.

## Docs to follow

- https://docs.langchain.com/langsmith/evaluate-complex-agent
- https://docs.langchain.com/langsmith/evaluation-approaches
- https://docs.langchain.com/langsmith/evaluation
- https://docs.langchain.com/langsmith/evaluation-concepts
- https://docs.langchain.com/langsmith/evaluation-types
- https://docs.langchain.com/langsmith/llm-as-judge
- https://docs.langchain.com/langsmith/trajectory-evals
- https://docs.langchain.com/langsmith/evaluate-rag-tutorial
- https://docs.langchain.com/langsmith/evaluate-on-intermediate-steps
- https://docs.langchain.com/langsmith/pytest
- https://docs.langchain.com/langsmith/cicd-pipeline-example
- https://docs.langchain.com/langsmith/online-evaluations-llm-as-judge
- https://docs.langchain.com/langsmith/dashboards
- https://docs.langchain.com/langsmith/alerts
- https://docs.langchain.com/oss/python/integrations/vectorstores/pinecone
- https://docs.langchain.com/oss/python/langgraph/add-memory
- https://docs.langchain.com/oss/python/langgraph/persistence
- https://docs.langchain.com/oss/python/langgraph/checkpointers
- https://docs.langchain.com/oss/python/langgraph/stores
- https://docs.langchain.com/oss/python/langgraph/interrupts
- https://docs.langchain.com/oss/python/langchain/guardrails
- https://github.com/PrithivirajDamodaran/FlashRank
- https://github.com/langchain-ai/langchain-community/issues/674
- https://docs.langchain.com/oss/python/integrations/retrievers/pinecone_rerank
- https://docs.langchain.com/langsmith/evaluate-rag-tutorial
- https://docs.langchain.com/langsmith/openevals
- https://vercel.com/docs/deployments/environments
- https://render.com/docs/free
- https://neon.com/faqs/free-plan-limits-and-quotas
- https://authjs.dev/getting-started/authentication/credentials
- https://authjs.dev/guides/integrating-third-party-backends
- https://github.com/laurentS/slowapi
- https://lawsofux.com/
- https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/

## Out of scope

Real payments, SSO, and CRM. Open-web search as knowledge. A required LangSmith Plus Agent Server. Deep Agents fleets.

## Submission

README quickstart, architecture diagram, LangSmith trace and experiment instructions, before/after table, judge calibration, known failures, and CI badge. Screen recording: FAQ answer with citations, refund proposal, human approve, ticket created, then one failed eval and the trace.

## Build order

Phases 0 to 7 in `docs/plans/slice-1-build-phases.md`, each a vertical slice accepted against PRD requirement ids. The implementation spec is `docs/spec.md` (also published as a GitHub issue labeled `ready-for-agent`). Phase 0 is `docs/plans/phase-0-handbook-v2.md`.
