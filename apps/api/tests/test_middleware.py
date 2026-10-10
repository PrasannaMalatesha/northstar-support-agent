"""The create_agent subgraph runs behind PII masking, call limits, and a lookup-failed path.

A scripted chat model stands in for Gemini, so no key or network is used.
"""

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from pydantic import Field

import northstar.agent_model as agent_model
import northstar.graph as graph
from northstar.graph import LOOKUP_FAILED_TEXT, _agent_draft
from northstar.handbook import Draft
from northstar.privacy import SECRET_REPLY


class Scripted(GenericFakeChatModel):
    seen: list = Field(default_factory=list)

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(" ".join(str(message.content) for message in messages))
        return super()._generate(messages, stop, run_manager, **kwargs)


def _desk_call(*ids: str) -> AIMessage:
    calls = [{"name": "desk", "args": {"question": "q"}, "id": call_id} for call_id in ids]
    return AIMessage(content="", tool_calls=calls)


def _use(monkeypatch, *replies: AIMessage) -> Scripted:
    model = Scripted(messages=iter(replies))
    monkeypatch.setattr(agent_model, "_agent_model", lambda: model)
    monkeypatch.delenv("AGENT_FALLBACK_MODEL", raising=False)
    return model


def _answer(asked: list):
    def draft_fn(question: str) -> Draft:
        asked.append(question)
        return Draft("answer", "Standard shipping takes 3 to 5 days. (SHIP-SLA)", ("SHIP-SLA",), {"SHIP-SLA": "strong"})

    return draft_fn


def test_the_model_never_sees_email_phone_or_a_full_card(monkeypatch):
    model = _use(monkeypatch, _desk_call("1"), AIMessage(content="Done."))
    asked = []
    question = "I am ana@example.com, phone 415-555-0100, card 4111 1111 1111 1111. When does it ship?"
    draft = _agent_draft(question, _answer(asked), "support_agent")
    assert draft.citations == ("SHIP-SLA",)
    assert asked == [question]
    seen = " ".join(model.seen)
    assert "ana@example.com" not in seen
    assert "415-555-0100" not in seen
    assert "4111 1111 1111 1111" not in seen


def test_the_desk_runs_once_even_when_the_model_asks_twice(monkeypatch):
    _use(monkeypatch, _desk_call("1", "2"), AIMessage(content="Done."))
    asked = []
    _agent_draft("When does it ship?", _answer(asked), "support_agent")
    assert len(asked) == 1


def test_a_failed_lookup_says_so_and_fills_in_no_facts(monkeypatch):
    _use(monkeypatch, _desk_call("1"), AIMessage(content="Sorry."))
    tries = []

    def broken(question: str) -> Draft:
        tries.append(question)
        raise ConnectionError("order system down")

    draft = _agent_draft("Where is order NS-1001?", broken, "support_agent")
    assert draft.decision == "lookup_failed"
    assert draft.text == LOOKUP_FAILED_TEXT
    assert draft.citations == ()
    assert len(tries) == 2


def test_a_secret_stops_the_turn_before_any_model_call(monkeypatch):
    model = _use(monkeypatch, _desk_call("1"), AIMessage(content="Done."))
    asked = []
    draft = _agent_draft("My key is sk-abcdefgh12345, what is the return window?", _answer(asked), "support_agent")
    assert draft.decision == "blocked"
    assert draft.text == SECRET_REPLY
    assert asked == []
    assert model.seen == []


def test_a_model_that_keeps_asking_stops_at_three_calls_inside_the_step_cap(monkeypatch):
    # The worst case run_limit allows: three model calls, each asking for the desk again.
    model = _use(monkeypatch, _desk_call("1"), _desk_call("2"), _desk_call("3"), _desk_call("4"))
    asked = []
    draft = _agent_draft("When does it ship?", _answer(asked), "support_agent")
    assert len(model.seen) == 3
    assert len(asked) == 1
    assert draft.citations == ("SHIP-SLA",)


def test_the_step_cap_is_enforced_and_the_desk_still_answers(monkeypatch):
    # Below the 26 steps a normal agent turn needs, LangGraph stops the subgraph.
    # The desk then decides without a model, as on any other model failure.
    monkeypatch.setattr(graph, "AGENT_RECURSION_LIMIT", 5)
    _use(monkeypatch, _desk_call("1"), AIMessage(content="Done."))
    asked = []
    draft = _agent_draft("When does it ship?", _answer(asked), "support_agent")
    assert draft.citations == ("SHIP-SLA",)
    assert asked == ["When does it ship?"]
