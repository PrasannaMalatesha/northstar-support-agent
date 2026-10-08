"""Score the current handbook answerer. This module is v0.

A later retrieval adapter replaces the answer function passed to score().
This file and its cases stay. Callers of answer() do not.
"""

from __future__ import annotations

from northstar.handbook import answer

# Expected sections are the handbook's own ids. They are not derived from answer().
CASES = (
    {
        "id": "apparel-window",
        "question": "How long is the return window for apparel?",
        "decision": "answer",
        "sections": ("REF-CATEGORY",),
    },
    {
        "id": "fourteen-day-trap",
        "question": "Apparel can be returned for 14 days, right?",
        "decision": "answer",
        "sections": ("REF-CATEGORY",),
    },
    {
        "id": "out-of-handbook",
        "question": "What is your favorite color?",
        "decision": "abstain",
        "sections": (),
    },
)


def score(answer_fn=answer) -> list[dict]:
    rows = []
    for case in CASES:
        draft = answer_fn(case["question"])
        missing = [section for section in case["sections"] if section not in draft.citations]
        decision_ok = draft.decision == case["decision"]
        rows.append(
            {
                "id": case["id"],
                "decision": draft.decision,
                "citations": list(draft.citations),
                "passed": decision_ok and not missing,
                "missing_sections": missing,
            }
        )
    return rows
