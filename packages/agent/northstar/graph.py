"""Route one turn to the refund path or the support path.

ponytail: these nodes call the desk functions. Handbook wording uses
Gemini when GOOGLE_API_KEY is set. No checkpointer here: the case row
holds the turn until PostgresSaver is the pause store.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Literal

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command
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
    return _fields(runtime.context.refund(state["question"]))


def support_agent(state: TurnState, runtime: Runtime[TurnTools]) -> dict:
    return _fields(runtime.context.support(state["question"]))


def compile_followup(state: TurnState) -> dict:
    return {"followup": state["text"]}


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


def turn_path(question: str, tools: TurnTools) -> list[str]:
    # ponytail: node names only. Append tool-call names when a node named
    # "tools" exists, as the complex-agent guide does.
    names = []
    for item in GRAPH.stream(
        {"question": question},
        context=tools,
        stream_mode="debug",
        subgraphs=True,
    ):
        chunk = item[-1]
        if isinstance(chunk, dict) and chunk.get("type") == "task":
            names.append(chunk["payload"]["name"])
    return names


def run_turn(question: str, tools: TurnTools, graph=None, thread_id: str | None = None) -> Draft:
    graph = graph or GRAPH
    config = None if thread_id is None else {"configurable": {"thread_id": thread_id}}
    result = graph.invoke({"question": question}, config, context=tools)
    return Draft(
        result["decision"],
        result["followup"],
        tuple(result["citations"]),
        result["match"],
        tuple(result["steps"]),
    )
