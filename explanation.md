# Explanation

How to talk through this project. The build has not started. What follows is the design, in the order it was decided, and why.

Walk the pictures in [`architecture.md`](architecture.md) in the order that file lists. Each diagram cites the LangChain, LangGraph, or LangSmith page it comes from. Product scope, including later support features, is in [`prd.md`](prd.md). The technical requirements document is not written until it is asked for.

## What we are building

A support agent for a fictional store, Northstar Goods. It answers company questions from written policy, looks up orders, and proposes refunds. A person approves a refund before any ticket is created.

The take-home asked for a small agent with a tool and retrieval, a dataset of normal and failing cases, deterministic checks, an LLM judge, traces, a before-and-after experiment, and an honest account of what still fails. That list is unchanged.

## Why this shape

A single prompt that both chats and refunds is hard to test. The official LangChain customer-support guide splits the work ([Evaluate a complex agent](https://docs.langchain.com/langsmith/evaluate-complex-agent)):

- An intent node chooses the path.
- A support path answers questions.
- A refund path handles refunds.
- `compile_followup` produces the string the user sees.

We use that shape so we can eval the router without running the whole graph, and eval the final sentence separately from the path that produced it.

We do not copy their music-store SQL bot. Their refund node writes immediately. Ours stops for a human, because a refund is a money action.

## Steps taken so far

1. Chose a support agent with refunds, not a refund-only bot, because support people ask policy questions too.
2. Locked LangChain, LangGraph, and LangSmith, because the eval story (datasets, experiments, traces, online judges) lives there.
3. Wrote policy docs as the only source of company rules. Section IDs are the citations. If retrieval is weak, the agent abstains instead of inventing a window or an amount.
4. Split graders. Code checks exact actions, routes, citations, tool order, and HITL. An LLM judge checks whether the wording is factually the same as the gold answer, and a second judge checks that claims sit in the retrieved text. Humans calibrate those judges on a small labeled set.
5. Adopted the official three experiments: final response, intent node alone, trajectory. The published trajectory score is `trajectory_subsequence` (fraction of expected steps found in order). Extra wasted steps are counted separately, because that official score does not punish them.
6. Stacked guardrails: cheap input blocks first, then PII redaction, then human approval, then an output check. A blocked input does not spend an agent-model call.
7. Split storage. Pinecone holds policy vectors. Postgres holds chats, the HITL pause, cross-thread user memory, orders, and tickets.
8. A refund proposal pauses the graph thread with `interrupt`. The lead's decision resumes it. The case row is still the ticket.

## Why Next.js and FastAPI

The console is a web app people can open. Next.js is the UI. The agent, tools, and evals are Python, which is where LangGraph and LangSmith’s Python SDK are documented. FastAPI is the boundary so the browser never sees the model key, and so a refund resume is a normal HTTP call with a `thread_id`.

## Why Pinecone and Postgres

Policy search and conversation history are different problems.

Pinecone is the vector index for policy chunks (`PineconeVectorStore` in LangChain). Metadata carries `section_id`, so a citation can be checked against the registry. Chat text does not go in this index. Putting transcripts in the vector store would let the model treat an old reply as if it were policy.

Postgres holds three kinds of memory, matching the LangGraph docs:

- Short-term, one conversation: `PostgresSaver`, keyed by `thread_id`. This is also what makes human approval work. The graph pauses, the process can restart, and resume uses the same thread. An in-memory saver loses that pause on restart.
- Long-term, across conversations: `PostgresStore`, namespaced by user. Preferences and facts the user already gave. Not a substitute for the policy corpus.
- Business rows: orders and refund tickets, so a ticket has an id, an amount, and who approved it.

Local development uses Postgres too, so a bug that only appears with the real checkpointer shows up before deploy.

## Why evals are part of the design, not a later add-on

A correct refund sentence can still come from the wrong tools, or from a ticket created before approval. So we score:

- the final `followup` text
- the router by itself
- the ordered steps, with partial credit
- extra steps that burn tokens
- citations and HITL as hard failures
- latency, token cost, and error rate from the LangSmith trace

CI runs the offline set before deploy. Live traffic gets reference-free judges and dashboards. A bad live trace becomes a new dataset row, then an offline test, then a fix.

## Why this reranker, and why retrieval is graded by code

Vector search is good at finding the neighborhood and bad at ordering it. A reranker reads the question and each chunk together, then reorders them. The agent sees only the top 4 chunks, so the order decides the answer. We call the `flashrank` package directly, model `ms-marco-MiniLM-L-12-v2`, because it runs on a CPU without Torch, fits the free server, and costs nothing per call. The LangChain wrapper lived in `langchain-community`, which was sunset on 2026-05-22, so the adapter does not import it. That means the evals test the same reranker that production runs. Pinecone's hosted reranker, `bge-reranker-v2-m3`, allows 500 requests a month on the Starter plan, which a few CI runs would spend.

Every labeled case says which handbook sections should come back. So "did retrieval find the right section?" is a lookup, not an opinion. Plain code grades it as recall and rank. The LLM judges are kept for things only a reader can decide: whether the draft agrees with the gold answer, whether every claim is in the retrieved text, and whether it helps the customer.

## Why the agent is built from LangChain's prebuilt pieces

Most ways an AI app breaks in production are already handled by LangChain middleware: retries on rate limits, a fallback model, caps on tool and model calls, PII redaction, the human approval pause, and summarizing long chats. The two specialist agents are built with `create_agent` so these attach by configuration instead of custom code. The router stays a plain LangGraph graph so the official single-step and trajectory evals still apply.

## Why the agent sees a summary of past cases, not old chats

Old transcripts cost tokens, carry personal data, and can mislead the model. A short record (past outcomes, open tickets, refunded lines) gives the agent what it needs to avoid a second refund. Nothing else from the past is passed in.

## How answer quality is scored

Code checks anything with a fixed answer: the action, the amount, the route, whether the right handbook section was retrieved, and whether every citation exists. Judges score only what needs reading: whether the reply means the same as the gold answer, and whether every claim is in the retrieved text. A judge runs only after the code checks pass, which keeps judge cost down. Before and after versions are compared row by row against a pinned baseline, and also pairwise.

## How login and limits protect the app

Only staff with an account created by an admin can sign in. Passwords are stored as argon2id hashes. The browser holds only an encrypted cookie. The Next.js server unlocks it and calls the Python API on the user's behalf, so no backend token or model key ever reaches the browser. The API checks the token and the person's role on every call, so hiding a button is not the only protection.

Limits sit at four levels. Login attempts lock after repeated failures. Request rates are capped per person. A daily model budget caps spend per person. The model client itself backs off when the provider says slow down. The limits that must survive a restart, the lockouts and the budgets, live in Postgres.

## Why three environments

A change goes from a feature branch to `dev`, then `uat`, then `prod`, always by pull request. Fast tests run on the way into `dev`. The full test split and the release bar run on the way into `uat`. A person approves the way into `prod`. Each environment has its own database branch, handbook namespace, and trace project, so a test in `uat` cannot touch production data. `main` always shows what is live.

## Why the desk is laid out this way

The specialist and the lead work under time pressure, so the case desk reads in one fixed order: the decision first, then the evidence for it, then the context, then the process. The single accent color only ever means "waiting for approval", so it is impossible to miss (Von Restorff). A lead sees three controls, a specialist sees none (Hick's Law), and the controls are large and spaced so approve is not hit by accident (Fitts's Law, WCAG 2.5.8). Four citations and five past cases keep the screen inside what a person can hold at once (Miller's Law). The first step appears within 400 ms of sending, so nobody wonders whether the click worked (Doherty Threshold). Accessibility is WCAG 2.2 AA because a staff tool is used all day by many people, and the checks are automated so they don't quietly slip. Staff also see the customer's past cases, because the person approving a refund should see the same history the agent used.

## What to say if asked about a failure

Open the trace. See whether retrieval, the router, a tool argument, the interrupt, or the final wording failed. Add one example whose expected answer matches a real policy section. Re-run that example, then the test split. Change the layer that failed: the doc, the index, the router, the tool, or the approval gate.

## Why the handbook comes first

Every later ticket cites a section id. The handbook was written and frozen as `northstar-policy-v2` before any agent code, so retrieval, prompts, and labeled cases all point at rules that will not move under them. Where two sections use the same numeral, they are different clocks: damage is 14 days from delivery, a lost package is 14 days from the ship date, and a price drop is 14 days from delivery. Each sentence lives in one section.

## What is not built yet

No application code, no index, no database, and no experiment results. `correction.md` is where later bugs and approach changes go.
