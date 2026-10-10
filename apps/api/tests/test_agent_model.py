import os

from northstar.agent_model import _load_local_env, handbook_reply
from northstar.retrieve import retrieved_answer


def test_pytest_does_not_load_local_secrets(monkeypatch):
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "yes")
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    _load_local_env()
    assert os.environ.get("LANGSMITH_TRACING") is None


def test_a_test_run_keeps_the_retrieved_handbook_draft(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "present")
    question = "How long is the return window for apparel?"
    assert handbook_reply(question) == retrieved_answer(question)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr("northstar.agent_model._load_local_env", lambda: None)
    assert handbook_reply(question) == retrieved_answer(question)


def test_every_model_call_has_a_timeout_and_one_retry_layer(monkeypatch):
    import northstar.agent_model as agent_model

    monkeypatch.setenv("GOOGLE_API_KEY", "present")
    monkeypatch.setenv("AGENT_FALLBACK_MODEL", "gemini-fallback")
    cached = (agent_model._model, agent_model._wording_model, agent_model._picker, agent_model._agent_model)
    for model in cached:
        model.cache_clear()
    try:
        direct, agent, fallback = agent_model._model(), agent_model._agent_model(), agent_model._fallback_model()
        wording, picker = agent_model._wording_model(), agent_model._picker()
    finally:
        for model in cached:
            model.cache_clear()
    assert direct.timeout == agent.timeout == fallback.timeout == wording.timeout == picker.timeout == 20
    # google-genai counts attempts including the first request.
    assert direct.max_retries == wording.max_retries == picker.max_retries == 3  # direct calls: the client retries
    assert agent.max_retries == fallback.max_retries == 1  # ModelRetryMiddleware retries instead


def test_a_turn_runs_under_the_router_step_cap():
    from northstar.graph import TURN_RECURSION_LIMIT, TurnTools, run_turn
    from northstar.handbook import Draft

    seen = {}

    class _Graph:
        def invoke(self, state, config=None, context=None):
            seen["config"] = config
            return {"decision": "answer", "text": "x", "citations": [], "match": {}, "steps": []}

    answer = Draft("answer", "x", (), {}, ())
    run_turn("q", TurnTools(lambda _q: answer, lambda _q: answer), graph=_Graph())
    assert seen["config"]["recursion_limit"] == TURN_RECURSION_LIMIT == 10


class _Picker:
    def __init__(self, reply):
        self.reply, self.seen = reply, []

    def invoke(self, messages, **_kwargs):
        from langchain_core.messages import AIMessage

        self.seen.append(messages[-1]["content"])
        if isinstance(self.reply, Exception):
            raise self.reply
        return AIMessage(content=self.reply)


def _abstained():
    from northstar.handbook import ABSTAIN_TEXT, Draft

    return Draft("abstain", ABSTAIN_TEXT, (), {}, retrieved=(("CO-SCOPE", 0.042), ("SHIP-REGIONS", 0.024)))


def test_on_an_abstain_the_model_may_pick_only_among_the_reranked_sections(monkeypatch):
    import northstar.agent_model as agent_model

    picker = _Picker("SHIP-REGIONS, REF-GIFT")
    monkeypatch.setattr(agent_model, "_picker", lambda: picker)
    draft = agent_model._picked("Can we ship an order to Canada?", _abstained(), None)
    assert draft.decision == "answer"
    assert draft.citations == ("SHIP-REGIONS",)  # REF-GIFT was not a candidate
    assert draft.match == {"SHIP-REGIONS": "weak"}
    assert "(SHIP-REGIONS)" in draft.text


def test_none_or_a_failed_call_keeps_the_abstain(monkeypatch):
    import northstar.agent_model as agent_model

    for reply in ("NONE", RuntimeError("down")):
        monkeypatch.setattr(agent_model, "_picker", lambda reply=reply: _Picker(reply))
        assert agent_model._picked("What is your favorite color?", _abstained(), None) is None


def test_the_earlier_question_is_given_to_the_picker(monkeypatch):
    import northstar.agent_model as agent_model

    picker = _Picker("NONE")
    monkeypatch.setattr(agent_model, "_picker", lambda: picker)
    agent_model._picked("And to Canada?", _abstained(), "Do you ship to all 50 states?")
    assert "Earlier question in this case: Do you ship to all 50 states?" in picker.seen[0]
