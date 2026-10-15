"""Langfuse beside LangSmith: off in tests and without keys, masked, one trace id per turn."""

from northstar import langfuse_tracing


def test_langfuse_is_off_in_tests_and_without_keys(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    assert langfuse_tracing.enabled() is False  # pytest sets PYTEST_CURRENT_TEST
    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    assert langfuse_tracing.enabled() is True
    monkeypatch.delenv("LANGFUSE_SECRET_KEY")
    assert langfuse_tracing.enabled() is False


def test_a_turn_has_one_trace_id_derived_from_its_run_id():
    first = langfuse_tracing.trace_id("01a12345-0000-7000-8000-000000000000")
    assert first == langfuse_tracing.trace_id("01a12345-0000-7000-8000-000000000000")
    assert len(first) == 32 and first != langfuse_tracing.trace_id("another-run")


def test_every_exported_attribute_is_masked_like_the_saved_text():
    from langfuse.types import MaskOtelSpansParams, OtelSpanData, OtelSpanIdentifier

    span_id = OtelSpanIdentifier(trace_id="a" * 32, span_id="b" * 16)
    data = OtelSpanData(
        trace_id="a" * 32,
        span_id="b" * 16,
        parent_span_id=None,
        instrumentation_scope_version=None,
        name="desk",
        attributes={
            "langfuse.observation.input": '{"question": "Email mira.shah@northstar.example, card 4111 1111 1111 1111"}',
            "langfuse.observation.output": "Customers reach Northstar at help@northstar.example.",
            "gen_ai.usage.input_tokens": 120,
        },
        resource_attributes={},
        instrumentation_scope_name="langfuse-sdk",
    )
    result = langfuse_tracing._mask(params=MaskOtelSpansParams(spans={span_id: data}))
    patched = result.span_patches[span_id].set_attributes
    assert "mira.shah@northstar.example" not in patched["langfuse.observation.input"]
    assert "4111 1111 1111 1111" not in patched["langfuse.observation.input"]
    # The published support address and numbers are left as they are.
    assert "langfuse.observation.output" not in patched and "gen_ai.usage.input_tokens" not in patched


def test_a_score_is_written_only_when_langfuse_is_on(monkeypatch):
    sent = []

    class Client:
        def create_score(self, **kwargs):
            sent.append(kwargs)

    monkeypatch.setattr(langfuse_tracing, "client", lambda: Client())
    langfuse_tracing.score("run-1", "policy_groundedness", 1)
    assert sent == []
    monkeypatch.setattr(langfuse_tracing, "enabled", lambda: True)
    langfuse_tracing.score("run-1", "policy_groundedness", 1)
    langfuse_tracing.score("run-1", "specialist_edit", "edited", comment="Before / After")
    assert [(s["name"], s["data_type"]) for s in sent] == [("policy_groundedness", "NUMERIC"), ("specialist_edit", "CATEGORICAL")]
    assert sent[0]["trace_id"] == langfuse_tracing.trace_id("run-1")


def test_a_turn_passes_the_langfuse_handler_only_when_langfuse_is_on(monkeypatch):
    from contextlib import contextmanager

    from northstar.graph import TurnTools, run_turn
    from northstar.handbook import Draft

    seen = []

    class Graph:
        def invoke(self, _input, config, context=None):
            seen.append(config)
            return {"decision": "answer", "text": "t", "followup": "t", "citations": [], "match": {}, "steps": []}

    finished = []

    class Observed:
        def __init__(self, callbacks):
            self.callbacks = callbacks

        def finish(self, output):
            finished.append(output)

    @contextmanager
    def turn(run_id, thread_id, question="", channel="desk"):
        yield Observed(["handler"] if run_id else [])

    fixed = Draft("answer", "t", (), {}, ())
    tools = TurnTools(refund=lambda _q: fixed, support=lambda _q: fixed)
    monkeypatch.setattr(langfuse_tracing, "turn", turn)
    monkeypatch.setattr("northstar.online.background", lambda *_a, **_k: None)
    run_turn("q", tools, graph=Graph())
    assert "callbacks" not in seen[-1] and "run_id" not in seen[-1]
    monkeypatch.setattr(langfuse_tracing, "enabled", lambda: True)
    draft = run_turn("q", tools, graph=Graph(), thread_id="case-1")
    assert seen[-1]["callbacks"] == ["handler"] and draft.run_id is not None
    assert finished[-1] == {"decision": "answer", "reply": "t", "citations": []}


def test_middleware_hook_spans_are_not_exported_but_agent_steps_are():
    from northstar.langfuse_tracing import _MIDDLEWARE_HOOK

    for hook in ("PIIMiddleware[email].before_model", "ModelCallLimitMiddleware.after_model", "ToolCallLimitMiddleware[desk].after_model"):
        assert _MIDDLEWARE_HOOK.search(hook), hook
    for step in ("support_agent", "model", "tools", "desk", "ChatGoogleGenerativeAI", "intent_classifier", "LangGraph"):
        assert not _MIDDLEWARE_HOOK.search(step), step


def test_the_app_s_safety_score_is_the_langsmith_rule(monkeypatch):
    from northstar import online
    from northstar.handbook import registry_ids

    ids = registry_ids()
    rule: dict = {}
    exec(online.safety_code(ids), rule)  # the code LangSmith runs on a trace
    turns = [
        ("answer", ["REF-WINDOW"]),
        ("answer", []),
        ("answer", ["NOT-A-SECTION"]),
        ("abstain", []),
        ("approve_refund", ["REF-ELIGIBILITY"]),
        ("approve_refund", []),
        ("escalate", ["ESC-LEGAL"]),
    ]
    for decision, citations in turns:
        expected = rule["perform_eval"]({"outputs": {"decision": decision, "citations": citations}})["safety"]
        assert online.safety(decision, citations, ids) == expected, (decision, citations)
    assert [online.safety(*turn, ids) for turn in turns] == [1, 0, 0, 1, 1, 0, 1]

    sent = []
    monkeypatch.setattr(langfuse_tracing, "score", lambda run_id, name, value, comment=None: sent.append((run_id, name, value)))
    assert online.record_safety("run-1", "answer", ("NOT-A-SECTION",)) == 0
    assert sent == [("run-1", "safety", 0)]
