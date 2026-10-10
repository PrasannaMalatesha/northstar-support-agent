"""Each agent turn has a deadline, and optional model steps give way to it (R36, issue #135).

Stand-in chat models take the live model path, so no key or network is used. A hanging model
moves the test clock by its attempts of MODEL_TIMEOUT_SECONDS and then fails, as the real client does.
"""

from datetime import timedelta
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from pydantic import Field

import northstar.agent_model as agent_model
from evals.experiments import photo_url
from northstar.agent_model import MODEL_TIMEOUT_SECONDS, attempts_left, turn_deadline
from northstar.handbook import ABSTAIN_TEXT
from northstar.photo import describe
from northstar.retrieve import retrieved_answer

QUESTION = "How long does a customer have to return a pair of shoes?"
SPANISH = "¿Cuántos días tengo para devolver unos zapatos?"
REWORDED = "Shoes can come back within 30 days. (REF-CATEGORY)"


class Model(GenericFakeChatModel):
    clock: Any
    hang: bool = True
    seen: list = Field(default_factory=list)

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        attempts = kwargs.get("max_retries", 1)
        self.seen.append(attempts)
        if self.hang:
            self.clock.advance(seconds=MODEL_TIMEOUT_SECONDS * attempts)
            raise TimeoutError("the model did not answer")
        return super()._generate(messages, stop, run_manager, **kwargs)


@pytest.fixture()
def models(monkeypatch, clock):
    """The live model path: a dummy key, no tracing, and stand-in models.

    pytest sets PYTEST_CURRENT_TEST again when the test body starts, so each test removes it itself.
    """
    for name in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "PINECONE_API_KEY", "AGENT_FALLBACK_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "present")
    monkeypatch.setattr(agent_model, "_load_local_env", lambda: None)
    desk_call = AIMessage(content="", tool_calls=[{"name": "desk", "args": {"question": "q"}, "id": "1"}])
    direct = Model(clock=clock, messages=iter([AIMessage(content=REWORDED)]))
    agent = Model(clock=clock, messages=iter([desk_call, AIMessage(content="Done.")]))
    monkeypatch.setattr(agent_model, "_model", lambda: direct)
    monkeypatch.setattr(agent_model, "_wording_model", lambda: direct)
    monkeypatch.setattr(agent_model, "_picker", lambda: direct)
    monkeypatch.setattr(agent_model, "_agent_model", lambda: agent)
    return direct, agent


def _ask(client, question):
    token = client.post(
        "/auth/login", json={"email": "specialist@northstar.example", "password": "northstar-specialist"}
    ).json()["access_token"]
    body = client.post("/cases/current/messages", headers={"Authorization": f"Bearer {token}"}, json={"question": question})
    return body.json()["messages"][-1]


def test_a_model_step_gets_only_the_attempts_that_fit_before_the_deadline(clock):
    assert attempts_left(3) == 3  # outside a turn, the per-call limits alone apply
    with turn_deadline(clock, 45):
        assert attempts_left(3) == 2
        clock.advance(seconds=30)
        assert attempts_left(3) == 0
    assert attempts_left(3) == 3


def test_a_turn_whose_model_hangs_returns_a_checked_reply_within_the_deadline_and_the_next_turn_works(client, clock, models, monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    direct, agent = models
    started = clock.now()
    draft = _ask(client, QUESTION)
    assert clock.now() - started <= timedelta(seconds=45)
    handbook = retrieved_answer(QUESTION)
    assert (draft["decision"], draft["body"], tuple(draft["citations"])) == ("answer", handbook.text, handbook.citations)
    assert agent.seen == [1, 1]  # two 20 s tries fit in 45 s, then the desk decided without a model
    assert direct.seen == []  # too little time was left to reword

    direct.hang = agent.hang = False
    draft = _ask(client, QUESTION)
    assert draft["body"] == REWORDED
    assert direct.seen == [2]  # a fresh deadline, so the wording ran again


def test_a_spanish_turn_whose_translation_hangs_still_gets_a_safe_reply(client, clock, models, monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    direct, agent = models
    started = clock.now()
    draft = _ask(client, SPANISH)
    assert clock.now() - started <= timedelta(seconds=45)
    assert direct.seen == [2]  # translating in used the time; translating out was skipped
    assert agent.seen == []
    # The desk read the untranslated words and abstained. No rule was made up.
    assert (draft["decision"], draft["body"], draft["citations"]) == ("abstain", ABSTAIN_TEXT, [])


@pytest.mark.parametrize("client", [{"turn_deadline_seconds": 10}], indirect=True)
def test_the_deadline_is_a_setting_and_a_short_one_skips_every_model_step(client, clock, models, monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    direct, agent = models
    direct.hang = agent.hang = False
    draft = _ask(client, SPANISH)
    assert direct.seen == agent.seen == []  # no 20 s attempt fits in 10 s
    assert (draft["decision"], draft["body"]) == ("abstain", ABSTAIN_TEXT)


def test_a_photo_is_left_undescribed_when_no_attempt_fits(clock, models, monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    direct, _agent = models
    direct.hang = False
    with turn_deadline(clock, 10):
        assert describe(photo_url("lamp-cracked.png"), "The desk lamp arrived damaged.") is None
    assert direct.seen == []
