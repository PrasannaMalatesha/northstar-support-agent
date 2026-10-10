"""Route one turn to the refund path or the support path.

ponytail: pytest and a missing model key call the desk functions directly.
A live key uses create_agent with that same function as the only tool.
The desk draft is kept. A proposal pauses in compile_followup only when
a checkpointer is attached. The case row still writes the ticket.
"""

from __future__ import annotations

import logging
import os
import random
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, Literal

from langgraph.config import get_config
from langgraph.constants import CONFIG_KEY_CHECKPOINTER
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt
from typing_extensions import TypedDict

from northstar.actions import PROPOSALS, gated
from northstar.handbook import Draft
from northstar.privacy import SECRET_REPLY


class TurnState(TypedDict, total=False):
    question: str
    text: str
    decision: str
    citations: list[str]
    match: dict[str, str]
    steps: list[str]
    retrieved: list[list]
    followup: str


@dataclass
class TurnTools:
    refund: Callable[[str], Draft]
    support: Callable[[str], Draft]


def asks_for_gated_action(question: str) -> bool:
    """A refund or any other action that waits for a lead. The table lives in northstar.actions."""
    return gated(question) is not None


def intent_classifier(
    state: TurnState,
) -> Command[Literal["refund_agent", "support_agent"]]:
    goto: Literal["refund_agent", "support_agent"] = (
        "refund_agent" if asks_for_gated_action(state["question"]) else "support_agent"
    )
    return Command(goto=goto)


def refund_agent(state: TurnState, runtime: Runtime[TurnTools]) -> dict:
    return _fields(_decide(state["question"], runtime.context.refund, "refund_agent"))


def support_agent(state: TurnState, runtime: Runtime[TurnTools]) -> dict:
    return _fields(_decide(state["question"], runtime.context.support, "support_agent"))


LOOKUP_FAILED_TEXT = "The lookup failed. No facts were filled in. Try again."

# Explicit step caps. The installed LangGraph defaults to 10007 supersteps, which is no cap at all.
# Measured: the router takes 3 steps. Each middleware hook is its own agent step, so a normal agent turn
# (two model calls, one desk call) needs a limit of 26, and the worst case run_limit=3 allows needs 43.
# https://docs.langchain.com/oss/python/langgraph/errors/GRAPH_RECURSION_LIMIT
TURN_RECURSION_LIMIT = 10
AGENT_RECURSION_LIMIT = 50


def _decide(question: str, draft_fn: Callable[[str], Draft], name: str) -> Draft:
    # https://docs.langchain.com/oss/python/langchain/agents
    from northstar.agent_model import attempts_left

    if os.environ.get("PYTEST_CURRENT_TEST") or not os.environ.get("GOOGLE_API_KEY"):
        return draft_fn(question)
    if not attempts_left(1):  # the turn's deadline is close: the desk decides without a model
        return draft_fn(question)
    return _agent_draft(question, draft_fn, name)


def _agent_draft(question: str, draft_fn: Callable[[str], Draft], name: str) -> Draft:
    from langchain.agents.middleware.pii import PIIDetectionError

    try:
        return _ask_agent(question, draft_fn, name)
    except PIIDetectionError:
        return Draft("blocked", SECRET_REPLY, (), {}, ())
    except Exception:
        # The model failed. The desk still decides, without a model.
        return draft_fn(question)


def _ask_agent(question: str, draft_fn: Callable[[str], Draft], name: str) -> Draft:
    from langchain.agents import create_agent
    from langchain_core.tools import tool

    from northstar.agent_model import _agent_model

    held: dict[str, Draft] = {}
    asked = question

    @tool
    def desk(question: str) -> str:
        """Return the Northstar desk decision for this question. Call once."""
        # ponytail: ignore the model argument. The routed question is the one the desk sees.
        draft = draft_fn(asked)
        held["draft"] = draft
        return draft.text

    create_agent(
        _agent_model(),
        [desk],
        system_prompt=(
            "Call the desk tool once with the specialist's question. "
            "Do not invent an amount, an order, or a rule."
        ),
        name=name,
        middleware=_middleware(held),
    ).invoke(
        {"messages": [{"role": "user", "content": question}]},
        # Set here, not inherited: the router's smaller cap would otherwise apply to this subgraph too.
        {"recursion_limit": AGENT_RECURSION_LIMIT},
    )
    if held.get("failed"):
        return Draft("lookup_failed", LOOKUP_FAILED_TEXT, (), {}, ())
    return held["draft"]


def _middleware(held: dict) -> list:
    """Built-in middleware on each create_agent subgraph. First in the list is outermost.

    https://docs.langchain.com/oss/python/langchain/middleware/built-in
    HumanInTheLoopMiddleware is not here: the subgraph has no ticket tool. The lead's
    decision in the API and the interrupt in compile_followup are the gate.
    SummarizationMiddleware is not here: the subgraph sees one message per turn.
    """
    from langchain.agents.middleware import (
        ModelCallLimitMiddleware,
        ModelFallbackMiddleware,
        ModelRetryMiddleware,
        PIIMiddleware,
        ToolCallLimitMiddleware,
        ToolErrorMiddleware,
        ToolRetryMiddleware,
    )

    from northstar.agent_model import _fallback_model, attempts_left
    from northstar.privacy import detector

    def pii(kind: str, strategy: str, find=None) -> PIIMiddleware:
        return PIIMiddleware(
            kind,
            strategy=strategy,
            detector=find,
            apply_to_input=True,
            apply_to_output=True,
            apply_to_tool_results=True,
        )

    def failed(exc: Exception, _request) -> str:
        held["failed"] = True
        logging.getLogger(__name__).warning("desk tool failed: %s", type(exc).__name__, exc_info=exc)
        return "Lookup failed. Do not fill in facts."

    fallback = _fallback_model()
    models = 1 if fallback is None else 2
    # Three tries per model, or only the tries that fit before the turn's deadline, shared by both models.
    tries = attempts_left(3 * models)
    if tries < models:
        fallback, models = None, 1
    return [
        pii("secret", "block", detector("secret")),
        pii("email", "redact", detector("email")),
        pii("credit_card", "mask"),
        pii("phone", "redact", detector("phone")),
        ModelCallLimitMiddleware(run_limit=3, exit_behavior="end"),
        ToolCallLimitMiddleware(tool_name="desk", run_limit=1),
        *([ModelFallbackMiddleware(fallback)] if fallback is not None else []),
        ModelRetryMiddleware(max_retries=max(tries // models - 1, 0), on_failure="error"),
        ToolErrorMiddleware(on_error=failed),
        ToolRetryMiddleware(max_retries=1, tools=["desk"], on_failure="error"),
    ]


def compile_followup(state: TurnState) -> dict:
    # https://docs.langchain.com/oss/python/langgraph/interrupts
    if state.get("decision") in PROPOSALS and _checkpointer_present():
        interrupt(state["decision"])
    return {"followup": state["text"]}


def _checkpointer_present() -> bool:
    conf = get_config().get("configurable") or {}
    return conf.get(CONFIG_KEY_CHECKPOINTER) is not None


def resume_turn(graph, thread_id: str, decision: str) -> None:
    config = {"configurable": {"thread_id": thread_id}}
    if graph.get_state(config).next:
        graph.invoke(Command(resume=decision), {**config, "recursion_limit": TURN_RECURSION_LIMIT})


def _fields(draft: Draft) -> dict:
    return {
        "text": draft.text,
        "decision": draft.decision,
        "citations": list(draft.citations),
        "match": dict(draft.match),
        "steps": list(draft.steps),
        "retrieved": [[section_id, score] for section_id, score in draft.retrieved],
    }


def _compile(checkpointer=None):
    builder = StateGraph(TurnState, context_schema=TurnTools)
    builder.add_node("intent_classifier", intent_classifier)
    builder.add_node("refund_agent", refund_agent)
    builder.add_node("support_agent", support_agent)
    builder.add_node("compile_followup", compile_followup)
    builder.add_edge(START, "intent_classifier")
    builder.add_edge("refund_agent", "compile_followup")
    builder.add_edge("support_agent", "compile_followup")
    builder.add_edge("compile_followup", END)
    return builder.compile(checkpointer=checkpointer)


GRAPH = _compile()


def task_names(stream) -> list[str]:
    """Node names, plus each tool name when the task is `tools`.

    The guide sample reads ``payload["input"]["messages"][-1].tool_calls``.
    This install's tools task puts the tool-call list on ``payload["input"]``.
    https://docs.langchain.com/langsmith/evaluate-complex-agent
    """
    names = []
    for item in stream:
        chunk = item[-1] if isinstance(item, tuple) else item
        if not isinstance(chunk, dict) or chunk.get("type") != "task":
            continue
        payload = chunk["payload"]
        names.append(payload["name"])
        if payload.get("name") == "tools":
            names.extend(_tool_call_names(payload.get("input")))
    return names


def _tool_call_names(incoming) -> list[str]:
    calls = incoming
    if isinstance(incoming, dict):
        messages = incoming.get("messages") or []
        last = messages[-1] if messages else None
        calls = last.get("tool_calls") if isinstance(last, dict) else getattr(last, "tool_calls", None)
    if not isinstance(calls, list):
        return []
    return [call["name"] for call in calls if isinstance(call, dict) and call.get("name")]


def turn_path(question: str, tools: TurnTools) -> list[str]:
    return task_names(
        GRAPH.stream(
            {"question": question},
            context=tools,
            stream_mode="debug",
            subgraphs=True,
        )
    )


@lru_cache(maxsize=1)
def _scrubbed_client():
    """LangSmith client that runs screen() on every traced input and output.

    Traces get the same masking as the saved text. https://docs.langchain.com/langsmith/mask-inputs-outputs
    """
    from langsmith import Client
    from langsmith.anonymizer import create_anonymizer

    from northstar.privacy import screen

    return Client(anonymizer=create_anonymizer(lambda text, _path: screen(text)))


def _turn_input(question: str) -> dict:
    # The case thread keeps the last turn's state. Clear followup so a paused turn
    # never shows the previous turn's reply.
    return {"question": question, "followup": ""}


def _upload_then_judge(
    run_id: str, question: str, decision: str, followup: str, citations: list[str], handover: str | None = None
) -> None:
    from langchain_core.tracers.langchain import wait_for_all_tracers

    from northstar import online

    wait_for_all_tracers()
    _scrubbed_client().flush()
    if handover is not None:
        online.record_handover(run_id, handover)
    online.record_judge(run_id, question, decision, followup, citations, random.random())


def run_turn(
    question: str,
    tools: TurnTools,
    graph=None,
    thread_id: str | None = None,
    handover: Callable[[str], str] | None = None,
) -> Draft:
    """One turn through the router. `handover` names why the turn handed over, from its decision, for the
    traced root run (issue #145). A turn without it records no hand-over."""
    from northstar.agent_model import _load_local_env

    _load_local_env()
    graph = graph or GRAPH
    traced = os.environ.get("LANGSMITH_TRACING", "").lower() == "true" and not os.environ.get("PYTEST_CURRENT_TEST")
    config: dict = {"recursion_limit": TURN_RECURSION_LIMIT}
    if thread_id is not None:
        config["configurable"] = {"thread_id": thread_id}
    run_id = None
    if traced:
        import langsmith

        # Name the LangGraph root run up front. Collected runs can list a child model call first.
        root = langsmith.uuid7()
        config["run_id"] = root
        run_id = str(root)
        with langsmith.tracing_context(client=_scrubbed_client()):
            result = graph.invoke(_turn_input(question), config, context=tools)
    else:
        result = graph.invoke(_turn_input(question), config, context=tools)
    # A turn that pauses for approval stops before compile_followup writes followup.
    followup = result.get("followup") or result["text"]
    if traced and run_id is not None:
        from northstar import online

        # After the turn, off the request: the trace upload (slow when LangSmith rate-limits), then the
        # hand-over reason and the judge on the uploaded root run. A failure is logged by background().
        reason = handover(result["decision"]) if handover else None
        online.background(_upload_then_judge, run_id, question, result["decision"], followup, list(result["citations"]), reason)
    return Draft(
        result["decision"],
        followup,
        tuple(result["citations"]),
        result["match"],
        tuple(result["steps"]),
        run_id,
        tuple((section_id, float(score)) for section_id, score in result.get("retrieved") or ()),
    )
