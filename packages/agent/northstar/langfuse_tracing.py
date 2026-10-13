"""Langfuse tracing and scores beside LangSmith. On only when its keys are set, and never in tests.

One agent turn is one trace named "support-turn": the LangGraph router, the agent, and the desk tool, with
each model call as a generation (model, tokens, cost). Its trace id is derived from the LangSmith root run
id, so a turn has the same identity on both platforms, and a score written later (an edit judged on close)
finds the trace. Every exported attribute goes through privacy.screen(), the masking the saved text gets.

https://langfuse.com/integrations/frameworks/langgraph
https://langfuse.com/docs/observability/features/masking
"""

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from functools import lru_cache

TRACE_NAME = "support-turn"


def enabled() -> bool:
    return (
        bool(os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"))
        and not os.environ.get("PYTEST_CURRENT_TEST")
    )


def sample_rate() -> float:
    """LANGFUSE_SAMPLE_RATE, 1.0 by default: the share of turns traced, to keep inside the free plan's units."""
    raw = os.environ.get("LANGFUSE_SAMPLE_RATE", "").strip()
    try:
        return min(1.0, max(0.0, float(raw))) if raw else 1.0
    except ValueError:
        return 1.0


@lru_cache(maxsize=1)
def client():
    from langfuse import Langfuse

    return Langfuse(
        base_url=os.environ.get("LANGFUSE_BASE_URL") or os.environ.get("LANGFUSE_HOST"),
        environment=os.environ.get("NORTHSTAR_ENV") or "local",
        sample_rate=sample_rate(),
        mask_otel_spans=_mask,
        should_export_span=_export,
    )


# create_agent runs each middleware hook as its own node: "PIIMiddleware[email].before_model" and the like.
# They are leaves with nothing to debug, and they were 16 of 22 observations a turn. Dropping them keeps
# the free plan's units for turns; the model calls, tools, and agent nodes stay.
_MIDDLEWARE_HOOK = re.compile(r"Middleware(\[[^\]]*\])?\.(before|after)_(model|agent)$")


def _export(span) -> bool:
    from langfuse import is_default_export_span

    return is_default_export_span(span) and not _MIDDLEWARE_HOOK.search(span.name or "")


def trace_id(run_id: str) -> str:
    from langfuse import Langfuse

    return Langfuse.create_trace_id(seed=run_id)


def _screened(value):
    from northstar.privacy import screen

    if isinstance(value, str):
        return screen(value)
    if isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
        return [screen(item) for item in value]
    return value


def _mask(*, params):
    """Mask every string attribute of an export batch. Langfuse drops the batch if this raises, so it must not."""
    from langfuse.types import MaskOtelSpansResult, OtelSpanPatch

    patches = {}
    for identifier, span in params.spans.items():
        changed = {}
        for key, value in span.attributes.items():
            masked = _screened(value)
            if masked != (list(value) if isinstance(value, tuple) else value):
                changed[key] = masked
        if changed:
            patches[identifier] = OtelSpanPatch(set_attributes=changed)
    return MaskOtelSpansResult(span_patches=patches)


# Inside a Langfuse experiment item, the item's trace and span. The desk target reaches the API through a test
# client on another thread, where the item's context is gone; a turn started meanwhile nests under the item.
_experiment_parent: dict | None = None


@contextmanager
def nested_under_current():
    """Nest the turns started inside this block under the current Langfuse observation (an experiment item).

    A module variable, not a context variable, because the turn runs on the test client's thread. Experiment
    items on the desk run one at a time, so one value at a time is enough."""
    global _experiment_parent
    langfuse = client() if enabled() else None
    trace, span = (langfuse.get_current_trace_id(), langfuse.get_current_observation_id()) if langfuse else (None, None)
    _experiment_parent = {"trace_id": trace, "parent_span_id": span} if trace and span else None
    try:
        yield
    finally:
        _experiment_parent = None


class Turn:
    """One agent turn: the callbacks to pass to the graph, and the reply to record when it ends."""

    def __init__(self, callbacks: list, span=None) -> None:
        self.callbacks = callbacks
        self._span = span

    def finish(self, output: dict) -> None:
        if self._span is not None:
            self._span.update(output=output)


@contextmanager
def turn(run_id: str | None, thread_id: str | None, question: str = "", channel: str = "desk"):
    """A root span "support-turn" for one agent turn, with the Langfuse handler running inside it.

    The root span holds the question as input and the reply as output. A model call or tool whose LangChain
    parent run the handler never saw (inside a node's middleware or tool executor) nests under it instead of
    starting a second root in the trace.
    """
    if run_id is None or not enabled():
        yield Turn([])
        return
    from langfuse import propagate_attributes
    from langfuse.langchain import CallbackHandler

    langfuse = client()
    with langfuse.start_as_current_observation(
        trace_context=_experiment_parent or {"trace_id": trace_id(run_id)},
        name=TRACE_NAME,
        as_type="agent",
        input={"question": question},
    ) as span:
        with propagate_attributes(
            trace_name=TRACE_NAME,
            session_id=thread_id,
            tags=[os.environ.get("NORTHSTAR_ENV") or "local", channel],
            metadata={"langsmith_run_id": run_id},
        ):
            yield Turn([CallbackHandler()], span)


def score(run_id: str, name: str, value, comment: str | None = None) -> None:
    """A score on the turn's trace. Categorical when the value is text, numeric otherwise."""
    if not enabled():
        return
    client().create_score(
        trace_id=trace_id(run_id),
        name=name,
        value=value,
        data_type="CATEGORICAL" if isinstance(value, str) else "NUMERIC",
        comment=comment,
    )


def flush() -> None:
    if enabled():
        client().flush()
