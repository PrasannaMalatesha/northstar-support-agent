"""Release bar from prd.md. A miss is a list entry. Empty means the bar passed.

ponytail: online_checks is the sampling rule only. Wire it to LangSmith when live runs exist.
"""

from __future__ import annotations

import math

ACTION_FLOOR = 0.8
LATENCY_P95_SECONDS = 10
CHUNK_CAP = 4
_CITED = frozenset({"answer", "approve_refund", "partial_credit", "deny", "escalate"})


def bad_citation(citations, registry) -> bool:
    return any(section not in registry for section in citations)


def missing_citation(decision: str, citations) -> bool:
    return decision in _CITED and not citations


def p95(samples: list[float]) -> float:
    ordered = sorted(samples)
    rank = math.ceil(0.95 * len(ordered)) - 1
    return ordered[rank]


def gates(rows: list[dict]) -> list[str]:
    misses = []
    if not rows:
        return ["no rows"]
    correct = sum(1 for row in rows if row["passed"]) / len(rows)
    if correct < ACTION_FLOOR:
        misses.append("action correct")
    if any(row["ticket"] for row in rows):
        misses.append("ticket without approval")
    if any(row["bad_citation"] for row in rows):
        misses.append("invalid citation")
    if any(missing_citation(row["decision"], row["citations"]) for row in rows):
        misses.append("missing citation")
    if any(row["wanted"] == "abstain" and row["decision"] != "abstain" for row in rows):
        misses.append("abstain")
    if p95([row["seconds"] for row in rows]) >= LATENCY_P95_SECONDS:
        misses.append("latency")
    if any(len(row["citations"]) > CHUNK_CAP or row["decision"] == "quota" for row in rows):
        misses.append("token cap")
    return misses


def online_checks(decision: str, edited: bool, sample: float) -> dict[str, bool]:
    judge = decision in {"abstain", "escalate"} or edited or sample < 0.1
    return {"safety": True, "judge": judge}
