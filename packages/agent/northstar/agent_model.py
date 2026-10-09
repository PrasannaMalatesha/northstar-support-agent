"""Handbook wording from Gemini. Citations stay on the retrieved sections.

ponytail: pytest keeps the retrieved draft so the labeled strings stay put.
The server calls Gemini when GOOGLE_API_KEY is set. Refund amounts stay in code.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

from northstar.handbook import Draft
from northstar.retrieve import retrieved_answer

AGENT_MODEL_DEFAULT = "gemini-3-flash-preview"


def handbook_reply(question: str) -> Draft:
    draft = retrieved_answer(question)
    if draft.decision != "answer" or os.environ.get("PYTEST_CURRENT_TEST"):
        return draft
    _load_local_env()
    if not os.environ.get("GOOGLE_API_KEY"):
        return draft
    text = _phrase(question, draft.text)
    if not text:
        return draft
    if not any(section_id in text for section_id in draft.citations):
        text = f"{text.rstrip()}\n{draft.text}"
    return Draft(draft.decision, text, draft.citations, draft.match, draft.steps)


def _phrase(question: str, handbook_lines: str) -> str:
    attempts = attempts_left(DIRECT_ATTEMPTS)
    if not attempts:  # the turn's deadline is close: the cited handbook text stands
        return ""
    try:
        reply = _model().invoke(
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


def _gemini(name: str, attempts: int):
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=name,
        google_api_key=os.environ["GOOGLE_API_KEY"],
        temperature=0,
        timeout=MODEL_TIMEOUT_SECONDS,
        max_retries=attempts,
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
def _agent_model():
    """For the create_agent subgraphs, whose ModelRetryMiddleware does the retrying."""
    return _gemini(os.environ.get("AGENT_MODEL") or AGENT_MODEL_DEFAULT, AGENT_ATTEMPTS)
