"""Answer a handbook question from the frozen markdown, or abstain.

ponytail: term overlap. The reranked path is retrieved_answer(). This
function stays the v0 scorer passed to the evals by default.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

from northstar.actions import PROPOSALS

_HEADING = re.compile(r"^[A-Z][A-Z0-9]+(?:-[A-Z0-9]+)+$")
_STOP = frozenset(
    """
    a an the and or of to for in on at by with from into over how can
    does do did is are was were be been being what when where which who
    why will would should could i you we they my your our their this that
    it its not no yes please about have has had
    """.split()
)


STEPS = ("Classifying the question", "Reading the handbook")


@dataclass(frozen=True)
class Draft:
    decision: str
    text: str
    citations: tuple[str, ...]
    match: dict[str, str]
    steps: tuple[str, ...] = STEPS
    # LangSmith root run of the turn, so a later edit can score that same trace.
    run_id: str | None = None


ABSTAIN_TEXT = (
    "No handbook section covers that. "
    "Ask about returns, shipping, warranty, orders, payments, promotions, or the account."
)


def policy_dir() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "data" / "policy"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("data/policy")


def answer(question: str, directory: Path | None = None) -> Draft:
    directory = directory or policy_dir()
    sections = _sections(directory)
    query = _tokens(question)
    if not query or not sections:
        return _abstain()

    bags = [(section_id, body, set(_tokens(body))) for section_id, body in sections]
    document_frequency = {
        token: sum(1 for _, _, bag in bags if _hit(token, bag)) for token in set(query)
    }

    ranked: list[tuple[float, str, str]] = []
    for section_id, body, bag in bags:
        hits = [token for token in query if _hit(token, bag)]
        if len(hits) * 2 <= len(query):
            continue
        weight = sum(
            math.log((len(bags) + 1) / (document_frequency[token] + 1)) for token in hits
        )
        ranked.append((weight, section_id, body))
    ranked.sort(reverse=True)
    chosen = ranked[:4]
    if not chosen:
        return _abstain()

    best = chosen[0][0]
    lines = []
    citations = []
    match: dict[str, str] = {}
    for weight, section_id, body in chosen:
        rule = _rule(body)
        if not rule:
            continue
        lines.append(f"{rule} ({section_id})")
        citations.append(section_id)
        # ponytail: top band is strong, the rest weak. retrieved_answer()
        # uses the FlashRank score for the same split.
        match[section_id] = "strong" if weight >= best * 0.75 else "weak"
    if not lines:
        return _abstain()
    return Draft("answer", "\n".join(lines), tuple(citations), match)


def _abstain() -> Draft:
    return Draft("abstain", ABSTAIN_TEXT, (), {})


_CITED = frozenset({"answer", "escalate"}) | PROPOSALS


def registry_ids() -> set[str]:
    text = (policy_dir() / "SECTION_IDS.md").read_text()
    return {
        line.split("|")[1].strip()
        for line in text.splitlines()
        if line.startswith("| ") and line.split("|")[1].strip() not in {"Id", "---"}
    }


def guard_draft(draft: Draft) -> Draft:
    """Every saved draft. A policy claim with a bad or missing section becomes an abstain."""
    legal = registry_ids()
    bad = any(section_id not in legal for section_id in draft.citations)
    if bad or (draft.decision in _CITED and not draft.citations):
        return _abstain()
    return draft


def _sections(directory: Path) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for path in sorted(directory.glob("*.md")):
        if path.name == "SECTION_IDS.md":
            continue
        parts = path.read_text().split("\n## ")
        for part in parts[1:]:
            heading, _, body = part.partition("\n")
            section_id = heading.strip()
            if _HEADING.fullmatch(section_id):
                found.append((section_id, body))
    return found


def _hit(token: str, bag: set[str]) -> bool:
    if token in bag:
        return True
    if len(token) < 4:
        return False
    return any(word.startswith(token) or token.startswith(word) for word in bag if len(word) >= 4)


def _tokens(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if token not in _STOP and len(token) > 2
    ]


def _rule(body: str) -> str:
    match = re.search(r"\*\*Rule\*\*: (.+)", body)
    return match.group(1).strip() if match else ""
