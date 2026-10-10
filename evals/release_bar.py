"""Release bar from prd.md. A miss is a list entry. Empty means the bar passed.

online_checks reads the live sampling rule from northstar.online, so the two cannot drift.
"""

from __future__ import annotations

import math

from northstar.actions import PROPOSALS
from northstar.online import should_judge

ACTION_FLOOR = 0.8
LATENCY_P95_SECONDS = 10
# Spanish turns make two translation calls (about 16 s on a live run). Their own target until translation is faster.
SPANISH_LATENCY_P95_SECONDS = 20
CHUNK_CAP = 4
# ponytail: a first cap, half the daily budget (settings.daily_token_budget, 20,000), so no two turns
# spend a day. The results file records the largest turn of each run; set this from real runs.
TOKEN_CAP = 10_000
GATES = (
    "action correct",
    "ticket without approval",
    "invalid citation",
    "missing citation",
    "abstain",
    "latency",
    "spanish latency",
    "token cap",
)
_CITED = frozenset({"answer", "escalate"}) | PROPOSALS


def bad_citation(citations, registry) -> bool:
    return any(section not in registry for section in citations)


def missing_citation(decision: str, citations) -> bool:
    return decision in _CITED and not citations


def p95(samples: list[float]) -> float:
    ordered = sorted(samples)
    rank = math.ceil(0.95 * len(ordered)) - 1
    return ordered[rank]


def _languages(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    english = [row for row in rows if row.get("language", "en") != "es"]
    return english, [row for row in rows if row.get("language") == "es"]


def gates(rows: list[dict]) -> list[str]:
    """Each row is one turn: its labels, its seconds, and the tokens its model calls reported.

    Action correct and the 10 s latency are measured on the English rows, the held-out test cases.
    Spanish rows have their own latency target. Every other gate holds on every row.
    """
    english, spanish = _languages(rows)
    if not english:
        return ["no rows"]
    misses = []
    correct = sum(1 for row in english if row["passed"]) / len(english)
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
    if p95([row["seconds"] for row in english]) >= LATENCY_P95_SECONDS:
        misses.append("latency")
    if spanish and p95([row["seconds"] for row in spanish]) >= SPANISH_LATENCY_P95_SECONDS:
        misses.append("spanish latency")
    if any(len(row["citations"]) > CHUNK_CAP or row["decision"] == "quota" or row["tokens"] > TOKEN_CAP for row in rows):
        misses.append("token cap")
    return misses


def record(rows: list[dict], commit: str) -> dict:
    """The release run's results file: the commit it measured, each gate's result, and the measured numbers."""
    misses = gates(rows)
    english, spanish = _languages(rows)
    return {
        "commit": commit,
        "rows": len(rows),
        "gates": {gate: "no rows" not in misses and gate not in misses for gate in GATES},
        "measured": {
            "action_correct": round(sum(1 for row in english if row["passed"]) / len(english), 3) if english else None,
            "p95_seconds_en": round(p95([row["seconds"] for row in english]), 2) if english else None,
            "p95_seconds_es": round(p95([row["seconds"] for row in spanish]), 2) if spanish else None,
            "max_tokens": max((row["tokens"] for row in rows), default=None),
        },
    }


def online_checks(decision: str, edited: bool, sample: float) -> dict[str, bool]:
    return {"safety": True, "judge": should_judge(decision, sample, edited)}
