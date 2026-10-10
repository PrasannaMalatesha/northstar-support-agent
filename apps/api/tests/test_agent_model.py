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
    agent_model._model.cache_clear()
    agent_model._agent_model.cache_clear()
    try:
        direct, agent, fallback = agent_model._model(), agent_model._agent_model(), agent_model._fallback_model()
    finally:
        agent_model._model.cache_clear()
        agent_model._agent_model.cache_clear()
    assert direct.timeout == agent.timeout == fallback.timeout == 20
    # google-genai counts attempts including the first request.
    assert direct.max_retries == 3  # wording, translation, photo: the client retries
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
