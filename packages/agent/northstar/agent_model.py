"""Handbook wording from Gemini. Citations stay on the retrieved sections.

ponytail: pytest keeps the retrieved draft so the labeled strings stay put.
The server calls Gemini when GOOGLE_API_KEY is set. Refund amounts stay in code.
"""

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

from northstar.handbook import Draft
from northstar.retrieve import retrieved_answer

AGENT_MODEL_DEFAULT = "gemini-3-flash-preview"


def handbook_reply(question: str, earlier: str | None = None) -> Draft:
    """The handbook draft. `earlier` is the case's previous question, so a follow-up such as
    "what should I tell her about sending it back?" can be read in context."""
    draft = retrieved_answer(question)
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return draft
    _load_local_env()
    if not os.environ.get("GOOGLE_API_KEY"):
        return draft
    if draft.decision == "abstain" and draft.retrieved:
        draft = _picked(question, draft, earlier) or draft
    if draft.decision != "answer":
        return draft
    text = _phrase(question, draft.text)
    if not text:
        return draft
    if not any(section_id in text for section_id in draft.citations):
        text = f"{text.rstrip()}\n{draft.text}"
    return Draft(draft.decision, text, draft.citations, draft.match, draft.steps)


_SECTION_ID = re.compile(r"\b[A-Z]{2,5}(?:-[A-Z]+)+\b")


def _picked(question: str, draft: Draft, earlier: str | None) -> Draft | None:
    """When the reranker keeps no section, the model picks from its top few, or none.

    The small reranker scores some plain questions near zero ("Can we ship an order to Canada?" gives
    SHIP-REGIONS 0.02 against a 0.2 threshold) although it ranks the right section near the top. Picked
    sections are only ever the reranker's own candidates, cited as weak. NONE keeps the abstain.
    """
    from northstar.handbook import _rule, _sections, policy_dir

    attempts = attempts_left(DIRECT_ATTEMPTS)
    if not attempts:
        return None
    bodies = dict(_sections(policy_dir()))
    candidates = [section_id for section_id, _ in draft.retrieved if section_id in bodies]
    if not candidates:
        return None
    lines = "\n".join(f"{section_id}: {_rule(bodies[section_id])}" for section_id in candidates)
    context = f"Earlier question in this case: {earlier}\n" if earlier else ""
    try:
        reply = _picker().invoke(
            [
                {
                    "role": "system",
                    "content": (
                        "You pick handbook sections for a support question. Reply with the ids of the sections "
                        "whose rule directly answers the latest question, comma separated, or NONE if no section "
                        "answers it. Use the earlier question only to understand what the latest one refers to. "
                        "Do not guess."
                    ),
                },
                {"role": "user", "content": f"{context}Latest question: {question}\n\nSections:\n{lines}"},
            ],
            max_retries=attempts,
        )
    except Exception:
        return None
    picked = [section_id for section_id in candidates if section_id in set(_SECTION_ID.findall(reply_text(reply)))]
    if not picked:
        return None
    text = "\n".join(f"{_rule(bodies[section_id])} ({section_id})" for section_id in picked)
    return Draft("answer", text, tuple(picked), {section_id: "weak" for section_id in picked}, draft.steps)


def _phrase(question: str, handbook_lines: str) -> str:
    attempts = attempts_left(DIRECT_ATTEMPTS)
    if not attempts:  # the turn's deadline is close: the cited handbook text stands
        return ""
    try:
        reply = _wording_model().invoke(
            [
                {
                    "role": "system",
                    "content": (
                        "You answer Northstar support questions. Use only the handbook lines. "
                        "Keep every section id that appears in parentheses. "
                        "Do not add a rule that is not in the lines."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Question: {question}\n\nHandbook lines:\n{handbook_lines}",
                },
            ],
            max_retries=attempts,
        )
    except Exception:
        return ""
    return reply_text(reply)


def reply_text(reply) -> str:
    """The plain text of a chat model reply. Gemini can return a list of parts."""
    content = getattr(reply, "content", "")
    if isinstance(content, list):
        pieces = []
        for part in content:
            if isinstance(part, str):
                pieces.append(part)
            elif isinstance(part, dict):
                pieces.append(str(part.get("text") or ""))
            else:
                pieces.append(str(getattr(part, "text", "") or ""))
        content = "".join(pieces)
    return str(content).strip()


def _load_local_env() -> None:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    for parent in Path(__file__).resolve().parents:
        env_file = parent / ".env"
        if not env_file.is_file():
            continue
        for line in env_file.read_text().splitlines():
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())
        break
    if os.environ.get("LANGSMITH_TRACING", "").lower() == "true":
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
        os.environ.setdefault("LANGCHAIN_CALLBACKS_BACKGROUND", "false")


# Every model call gets at most 3 attempts of at most 20 s each, and exactly one layer retries.
# google-genai counts `max_retries` as attempts including the first request (HttpRetryOptions.attempts).
# https://docs.langchain.com/oss/python/langchain/middleware/built-in
MODEL_TIMEOUT_SECONDS = 20
DIRECT_ATTEMPTS = 3  # calls outside create_agent: the client retries
AGENT_ATTEMPTS = 1  # calls inside create_agent: ModelRetryMiddleware retries instead

# One agent turn has a deadline (R36). Python cannot stop a call that has started, so a model step
# starts only when a whole attempt fits before the deadline, and it gets only the attempts that fit.
_TURN_END: ContextVar[tuple | None] = ContextVar("turn_end", default=None)


@contextmanager
def turn_deadline(clock, seconds: float):
    """Model steps inside this block check the time left on the app's clock."""
    token = _TURN_END.set((clock, clock.now() + timedelta(seconds=seconds)))
    try:
        yield
    finally:
        _TURN_END.reset(token)


def attempts_left(most: int) -> int:
    """Attempts of MODEL_TIMEOUT_SECONDS that fit before the turn's deadline, at most `most`. 0 skips the step."""
    turn = _TURN_END.get()
    if turn is None:
        return most
    clock, end = turn
    left = (end - clock.now()).total_seconds()
    return max(0, min(most, int(left // MODEL_TIMEOUT_SECONDS)))


def _gemini(name: str, attempts: int, thinking: str | None = None):
    """`thinking` sets Gemini 3's thinking level. Unset, the model's default applies (measured: thinking was
    80% of output tokens and 69% of the cost on 2026-10-09, results/conversation_check_2026-10-09.md)."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    extra = {"thinking_level": thinking} if thinking and name.startswith("gemini-3") else {}
    return ChatGoogleGenerativeAI(
        model=name,
        google_api_key=os.environ["GOOGLE_API_KEY"],
        temperature=0,
        timeout=MODEL_TIMEOUT_SECONDS,
        max_retries=attempts,
        **extra,
    )


def _fallback_model():
    """The second model for ModelFallbackMiddleware. None when AGENT_FALLBACK_MODEL is unset."""
    name = os.environ.get("AGENT_FALLBACK_MODEL")
    return _gemini(name, AGENT_ATTEMPTS) if name else None


@lru_cache(maxsize=1)
def _model():
    """For handbook wording, translation, and the photo check. Each falls back safely on failure."""
    return _gemini(os.environ.get("AGENT_MODEL") or AGENT_MODEL_DEFAULT, DIRECT_ATTEMPTS)


@lru_cache(maxsize=1)
def _wording_model():
    """For handbook wording. Low thinking kept every fact in the 2026-10-09 budget test; minimal dropped some."""
    return _gemini(os.environ.get("AGENT_MODEL") or AGENT_MODEL_DEFAULT, DIRECT_ATTEMPTS, "low")


@lru_cache(maxsize=1)
def _picker():
    """For picking sections on an abstain: a short choice among a few ids."""
    return _gemini(os.environ.get("AGENT_MODEL") or AGENT_MODEL_DEFAULT, DIRECT_ATTEMPTS, "minimal")


@lru_cache(maxsize=1)
def _agent_model():
    """For the create_agent subgraphs, whose ModelRetryMiddleware does the retrying.

    The agent only calls the one desk tool, so it needs no thinking.
    """
    return _gemini(os.environ.get("AGENT_MODEL") or AGENT_MODEL_DEFAULT, AGENT_ATTEMPTS, "minimal")
