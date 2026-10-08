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
