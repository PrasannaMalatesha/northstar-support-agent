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
import re
from dataclasses import dataclass
from typing import Callable, Literal

from langgraph.config import get_config
from langgraph.constants import CONFIG_KEY_CHECKPOINTER
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt
from typing_extensions import TypedDict

from northstar.handbook import Draft


class TurnState(TypedDict, total=False):
    question: str
    text: str
    decision: str
    citations: list[str]
    match: dict[str, str]
    steps: list[str]
    followup: str


@dataclass
class TurnTools:
    refund: Callable[[str], Draft]
    support: Callable[[str], Draft]


def asks_for_refund(question: str) -> bool:
    return re.search(r"\brefunds?\b|\bcredit\b", question.lower()) is not None


def intent_classifier(
    state: TurnState,
) -> Command[Literal["refund_agent", "support_agent"]]:
    goto: Literal["refund_agent", "support_agent"] = (
        "refund_agent" if asks_for_refund(state["question"]) else "support_agent"
    )
    return Command(goto=goto)


def refund_agent(state: TurnState, runtime: Runtime[TurnTools]) -> dict:
    return _fields(_decide(state["question"], runtime.context.refund, "refund_agent"))


def support_agent(state: TurnState, runtime: Runtime[TurnTools]) -> dict:
    return _fields(_decide(state["question"], runtime.context.support, "support_agent"))


def _decide(question: str, draft_fn: Callable[[str], Draft], name: str) -> Draft:
    # https://docs.langchain.com/oss/python/langchain/agents
    if os.environ.get("PYTEST_CURRENT_TEST") or not os.environ.get("GOOGLE_API_KEY"):
        return draft_fn(question)
    try:
        return _ask_agent(question, draft_fn, name)
    except Exception:
        return draft_fn(question)


def _ask_agent(question: str, draft_fn: Callable[[str], Draft], name: str) -> Draft:
    from langchain.agents import create_agent
    from langchain_core.tools import tool

    from northstar.agent_model import _model

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
        _model(),
        [desk],
        system_prompt=(
            "Call the desk tool once with the specialist's question. "
            "Do not invent an amount, an order, or a rule."
        ),
        name=name,
    ).invoke({"messages": [{"role": "user", "content": question}]})
    return held["draft"]


_PAUSE = frozenset({"approve_refund", "partial_credit", "deny"})


def compile_followup(state: TurnState) -> dict:
    # https://docs.langchain.com/oss/python/langgraph/interrupts
    if state.get("decision") in _PAUSE and _checkpointer_present():
        interrupt(state["decision"])
    return {"followup": state["text"]}


def _checkpointer_present() -> bool:
    conf = get_config().get("configurable") or {}
    return conf.get(CONFIG_KEY_CHECKPOINTER) is not None


def resume_turn(graph, thread_id: str, decision: str) -> None:
    config = {"configurable": {"thread_id": thread_id}}
    if graph.get_state(config).next:
        graph.invoke(Command(resume=decision), config)


def _fields(draft: Draft) -> dict:
    return {
        "text": draft.text,
        "decision": draft.decision,
        "citations": list(draft.citations),
        "match": dict(draft.match),
        "steps": list(draft.steps),
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


def run_turn(question: str, tools: TurnTools, graph=None, thread_id: str | None = None) -> Draft:
    from northstar.agent_model import _load_local_env

    _load_local_env()
    graph = graph or GRAPH
    traced = os.environ.get("LANGSMITH_TRACING", "").lower() == "true" and not os.environ.get("PYTEST_CURRENT_TEST")
    config = {} if thread_id is None else {"configurable": {"thread_id": thread_id}}
    run_id = None
    if traced:
        # Name the LangGraph root run up front. Collected runs can list a child model call first.
        from langsmith import uuid7

        root = uuid7()
        config["run_id"] = root
        run_id = str(root)
    result = graph.invoke({"question": question}, config or None, context=tools)
    followup = result["followup"] if "followup" in result else result["text"]
    if traced:
        from langchain_core.tracers.langchain import wait_for_all_tracers

        wait_for_all_tracers()
        if run_id is not None:
            try:
                from northstar.online import record_judge

                record_judge(
                    run_id,
                    question,
                    result["decision"],
                    followup,
                    result["citations"],
                    random.random(),
                )
            except Exception:
                # The turn still returns. The log says the judge did not score it.
                logging.getLogger(__name__).warning("groundedness judge failed for run %s", run_id, exc_info=True)
    return Draft(
        result["decision"],
        followup,
        tuple(result["citations"]),
        result["match"],
        tuple(result["steps"]),
        run_id,
    )
