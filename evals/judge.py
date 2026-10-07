"""Teacher-quiz judge. It does not score without a model key, and it does not record agreement.

The rubric is the one in the complex-agent guide:
https://docs.langchain.com/langsmith/evaluate-complex-agent
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Callable, TypedDict

from evals.labeled import judges_may_score_test

GRADER_INSTRUCTIONS = """You are a teacher grading a quiz.

You will be given a QUESTION, the GROUND TRUTH (correct) RESPONSE, and the STUDENT RESPONSE.

Here is the grade criteria to follow:
(1) Grade the student responses based ONLY on their factual accuracy relative to the ground truth answer.
(2) Ensure that the student response does not contain any conflicting statements.
(3) It is OK if the student response contains more information than the ground truth response, as long as it is factually accurate relative to the  ground truth response.

Correctness:
True means that the student's response meets all of the criteria.
False means that the student's response does not meet all of the criteria.

Explain your reasoning in a step-by-step manner to ensure your reasoning and conclusion are correct."""


class Grade(TypedDict):
    """Compare the expected and actual answers and grade the actual answer."""

    reasoning: Annotated[str, ..., "Explain your reasoning for whether the actual response is correct or not."]
    is_correct: Annotated[bool, ..., "True if the student response is mostly or exactly correct, otherwise False."]


GradeFn = Callable[[str, str, str], bool]


def grader_messages(question: str, reference: str, response: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": GRADER_INSTRUCTIONS},
        {
            "role": "user",
            "content": (
                f"QUESTION: {question}\n"
                f"    GROUND TRUTH RESPONSE: {reference}\n"
                f"    STUDENT RESPONSE: {response}"
            ),
        },
    ]


JUDGE_MODEL_DEFAULT = "nvidia/nemotron-3-ultra-550b-a55b:free"
OPENROUTER_BASE = "https://openrouter.ai/api/v1"


def final_answer_correct(
    inputs: dict,
    outputs: dict,
    reference_outputs: dict,
    grade: GradeFn | None = None,
) -> bool | None:
    if grade is None:
        if not os.environ.get("OPENROUTER_API_KEY"):
            return None
        grade = _live_grade
    return bool(grade(inputs["question"], reference_outputs["response"], outputs["response"]))


def score_examples(
    rows: list[dict],
    grade: GradeFn | None = None,
    calibration: str | None = None,
) -> list[dict]:
    if calibration is None:
        calibration = Path("results/judge_calibration.md").read_text()
    allow_test = judges_may_score_test(calibration)
    scored = []
    for row in rows:
        if row.get("split") == "test" and not allow_test:
            scored.append({"id": row["id"], "is_correct": None})
            continue
        scored.append(
            {
                "id": row["id"],
                "is_correct": final_answer_correct(
                    {"question": row["question"]},
                    {"response": row["response"]},
                    {"response": row["reference"]},
                    grade=grade,
                ),
            }
        )
    return scored


def calibration_text(rows: list[dict]) -> str:
    agreed = sum(1 for row in rows if row["human"] == row["judge"])
    lines = [
        "# Judge calibration",
        "",
        "The quiz judge scored the handbook rows in train_judge.",
        "The student text is the handbook answerer. The ground truth is the gold section rule, or the abstain text.",
        "Desk rows in that split stay on code checks.",
        "",
        f"agreement: {agreed}/{len(rows)}",
        "",
    ]
    for row in rows:
        human = "correct" if row["human"] else "wrong"
        judge = "correct" if row["judge"] else "wrong"
        lines.append(f"- {row['id']}: human {human}, judge {judge}")
    lines.append("")
    lines.append("test split: open" if rows and agreed == len(rows) else "test split: closed")
    lines.append("")
    return "\n".join(lines)


def _live_grade(question: str, reference: str, response: str) -> bool:
    grade = _grader().invoke(grader_messages(question, reference, response))
    return bool(grade["is_correct"])


@lru_cache(maxsize=1)
def _grader():
    from langchain.chat_models import init_chat_model

    # The model id contains a colon (`:free`). Pass the provider separately
    # so that colon is not read as an OpenAI model prefix.
    name = os.environ.get("JUDGE_MODEL") or JUDGE_MODEL_DEFAULT
    return init_chat_model(
        name,
        model_provider="openai",
        base_url=OPENROUTER_BASE,
        api_key=os.environ["OPENROUTER_API_KEY"],
        temperature=0,
    ).with_structured_output(Grade, method="json_schema", strict=True)
