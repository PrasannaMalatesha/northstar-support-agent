from northstar.agent_model import handbook_reply
from northstar.retrieve import retrieved_answer


def test_a_test_run_keeps_the_retrieved_handbook_draft(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "present")
    question = "How long is the return window for apparel?"
    assert handbook_reply(question) == retrieved_answer(question)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr("northstar.agent_model._load_local_env", lambda: None)
    assert handbook_reply(question) == retrieved_answer(question)
