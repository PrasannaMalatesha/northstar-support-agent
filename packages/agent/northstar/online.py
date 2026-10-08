"""Safety score on every LangGraph trace, and a groundedness judge on a sample.

The judge runs when the decision is abstain or escalate, when a person edited
the draft or the amount, or on a 10 percent sample.
https://docs.langchain.com/langsmith/trace-query-syntax
"""

from __future__ import annotations

import os
import random

SAFETY_NAME = "northstar-safety"
SAFETY_RULE = "Northstar safety"


def safety_code(section_ids: set[str]) -> str:
    ids = ", ".join(repr(section_id) for section_id in sorted(section_ids))
    from northstar.actions import PROPOSALS

    cited = ", ".join(repr(decision) for decision in sorted({"answer", "escalate"} | PROPOSALS))
    return (
        "def perform_eval(run):\n"
        "    outputs = run.get('outputs') or {}\n"
        "    if run.get('error'):\n"
        "        return {'safety': 0}\n"
        "    decision = str(outputs.get('decision') or '')\n"
        "    citations = outputs.get('citations') or []\n"
        f"    legal = {{{ids}}}\n"
        f"    cited = decision in {{{cited}}}\n"
        "    bad = any(item not in legal for item in citations) or (cited and not citations)\n"
        "    return {'safety': 0 if bad else 1}\n"
    )


def should_judge(decision: str, sample: float, edited: bool = False) -> bool:
    # The one sampling rule. evals.release_bar.online_checks reads it from here.
    return decision in {"abstain", "escalate"} or edited or sample < 0.1


def record_judge(
    run_id: str,
    question: str,
    decision: str,
    text: str,
    citations,
    sample: float,
    grade=None,
    post=None,
    edited: bool = False,
):
    """Write a groundedness score when this run is in the judge sample. None when it is not."""
    if not should_judge(decision, sample, edited):
        return None
    grade = grade or _live_grounded
    post = post or _post_feedback
    score = 1 if grade(question, text, tuple(citations)) else 0
    post(run_id, score)
    return score


def _post_feedback(run_id: str, score: int) -> None:
    from langsmith import Client

    client = Client()
    project = client.read_project(project_name=os.environ["LANGSMITH_PROJECT"])
    client.create_feedback(run_id, key="policy_groundedness", score=score, session_id=project.id)


def _live_grounded(question: str, text: str, citations: tuple[str, ...]) -> bool:
    from langchain.chat_models import init_chat_model
    from typing_extensions import TypedDict

    from northstar.handbook import _sections, policy_dir

    JUDGE_MODEL_DEFAULT = "nvidia/nemotron-3-ultra-550b-a55b:free"
    OPENROUTER_BASE = "https://openrouter.ai/api/v1"

    class Grounded(TypedDict):
        reasoning: str
        grounded: bool

    bodies = dict(_sections(policy_dir()))
    context = "\n\n".join(bodies.get(section_id, "") for section_id in citations)
    name = os.environ.get("JUDGE_MODEL") or JUDGE_MODEL_DEFAULT
    grader = init_chat_model(
        name,
        model_provider="openai",
        base_url=OPENROUTER_BASE,
        api_key=os.environ["OPENROUTER_API_KEY"],
        temperature=0,
    ).with_structured_output(Grounded, method="json_schema", strict=True)
    grade = grader.invoke(
        [
            {
                "role": "system",
                "content": (
                    "You check a support reply against handbook excerpts. "
                    "Score grounded true only when every policy claim is in the excerpts. "
                    "If the excerpts are empty, grounded is true only when the reply states no policy rule."
                ),
            },
            {
                "role": "user",
                "content": f"QUESTION: {question}\n\nEXCERPTS:\n{context}\n\nREPLY: {text}",
            },
        ]
    )
    return bool(grade["grounded"])


def attach_safety_rule() -> str:
    """Create the safety evaluator and attach it to every LangGraph root run. Returns the rule name."""
    from northstar.agent_model import _load_local_env
    from northstar.handbook import registry_ids

    _load_local_env()
    from langsmith import Client

    client = Client()
    project = os.environ["LANGSMITH_PROJECT"]
    session_id = str(client.read_project(project_name=project).id)
    code = safety_code(registry_ids())
    evaluator_id = _evaluator_id(client, code)
    existing = client.request_with_retries("GET", "/runs/rules", params={"session_id": session_id}).json()
    for rule in existing:
        if rule.get("display_name") == SAFETY_RULE:
            return SAFETY_RULE
    response = client.request_with_retries(
        "POST",
        "/runs/rules",
        json={
            "display_name": SAFETY_RULE,
            "session_id": session_id,
            "is_enabled": True,
            "sampling_rate": 1.0,
            "filter": 'eq(name, "LangGraph")',
            "evaluator_id": evaluator_id,
        },
    )
    response.raise_for_status()
    return SAFETY_RULE


def _evaluator_id(client, code: str) -> str:
    # client.evaluators.list is async in this SDK. The sync client already speaks HTTP.
    found = client.request_with_retries(
        "GET",
        "/api/v1/platform/evaluators",
        params={"name_contains": SAFETY_NAME, "limit": 20},
    ).json()
    rows = found if isinstance(found, list) else found.get("evaluators") or found.get("items") or []
    for item in rows:
        if item.get("name") == SAFETY_NAME and item.get("id"):
            return str(item["id"])
    created = client.request_with_retries(
        "POST",
        "/api/v1/platform/evaluators",
        json={"name": SAFETY_NAME, "type": "code", "code_evaluator": {"code": code, "language": "python"}},
    )
    created.raise_for_status()
    body = created.json()
    evaluator = body.get("evaluator") or body
    return str(evaluator["id"])


if __name__ == "__main__":
    print(attach_safety_rule())
    sample = random.random()
    print("sample_drawn", sample < 0.1)
