from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from evals.trajectory import extra_step_count, trajectory_subsequence
from langchain.agents import create_agent
from northstar.graph import TurnTools, task_names, turn_path
from northstar.handbook import Draft


def test_a_refund_path_scores_the_expected_steps_and_counts_a_ticket_call():
    def refund(_question: str) -> Draft:
        return Draft("approve_refund", "Approve.", ("REF-ELIGIBILITY",), {"REF-ELIGIBILITY": "strong"}, ())

    def support(_question: str) -> Draft:
        return Draft("answer", "Thirty days.", ("REF-CATEGORY",), {"REF-CATEGORY": "strong"}, ())

    path = turn_path("Please refund NS-1001", TurnTools(refund, support))
    reference = {"trajectory": ["intent_classifier", "refund_agent", "compile_followup"]}
    assert path == reference["trajectory"]
    assert trajectory_subsequence({"trajectory": path}, reference) == 1.0

    with_ticket = {"trajectory": [*path, "create_refund_ticket"]}
    assert trajectory_subsequence(with_ticket, reference) == 1.0
    assert extra_step_count(with_ticket, reference) == 1
    assert trajectory_subsequence({"trajectory": ["intent_classifier"]}, reference) is False


class _Bindable(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def test_a_nested_agent_records_the_tool_name_from_the_tools_task():
    @tool
    def desk(question: str) -> str:
        """Return the desk decision."""
        return "Approve."

    model = _Bindable(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[{"name": "desk", "args": {"question": "q"}, "id": "1", "type": "tool_call"}],
                ),
                AIMessage(content="done"),
            ]
        )
    )
    agent = create_agent(model, [desk])

    class State(TypedDict, total=False):
        question: str

    def refund_agent(state: State) -> dict:
        agent.invoke({"messages": [{"role": "user", "content": state["question"]}]})
        return {}

    builder = StateGraph(State)
    builder.add_node("refund_agent", refund_agent)
    builder.add_edge(START, "refund_agent")
    builder.add_edge("refund_agent", END)
    path = task_names(
        builder.compile().stream({"question": "Please refund"}, stream_mode="debug", subgraphs=True)
    )
    assert path == ["refund_agent", "model", "tools", "desk", "model"]
