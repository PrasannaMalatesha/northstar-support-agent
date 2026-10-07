"""Rerank the handbook sections that overlap the question.

ponytail: overlap picks the 20 candidates. Replace that pick with Pinecone
top-20 when PINECONE_API_KEY and the index exist. FlashRank stays.
"""

from __future__ import annotations

import math
import os
from functools import lru_cache
from pathlib import Path

from flashrank import Ranker, RerankRequest

from northstar.handbook import (
    ABSTAIN_TEXT,
    Draft,
    _hit,
    _rule,
    _sections,
    _tokens,
    policy_dir,
)

MODEL = "ms-marco-MiniLM-L-12-v2"
CANDIDATES = 20
KEEP = 4
# Lowest gold score on train_judge and dev is 0.41 (FAQ-HOURS).
# The 14-day trap's next section is 0.15. Abstain scores 0.
TAU = 0.2


def retrieved_answer(question: str, directory: Path | None = None) -> Draft:
    directory = directory or policy_dir()
    picked = _overlap(question, _sections(directory))
    if not picked:
        return _abstain()
    bodies = {section_id: body for section_id, body in picked}
    results = _ranker().rerank(
        RerankRequest(
            query=question,
            passages=[{"id": section_id, "text": body} for section_id, body in picked],
        )
    )
    kept = [row for row in results if float(row["score"]) >= _tau()][:KEEP]
    if not kept:
        return _abstain()

    best = float(kept[0]["score"])
    lines = []
    citations = []
    match: dict[str, str] = {}
    for row in kept:
        section_id = str(row["id"])
        rule = _rule(bodies[section_id])
        if not rule:
            continue
        lines.append(f"{rule} ({section_id})")
        citations.append(section_id)
        match[section_id] = "strong" if float(row["score"]) >= best * 0.75 else "weak"
    if not lines:
        return _abstain()
    return Draft("answer", "\n".join(lines), tuple(citations), match)


def _overlap(question: str, sections: list[tuple[str, str]]) -> list[tuple[str, str]]:
    query = _tokens(question)
    if not query or not sections:
        return []
    bags = [(section_id, body, set(_tokens(body))) for section_id, body in sections]
    document_frequency = {
        token: sum(1 for _, _, bag in bags if _hit(token, bag)) for token in set(query)
    }
    ranked: list[tuple[float, str, str]] = []
    for section_id, body, bag in bags:
        hits = [token for token in query if _hit(token, bag)]
        if not hits:
            continue
        weight = sum(
            math.log((len(bags) + 1) / (document_frequency[token] + 1)) for token in hits
        )
        ranked.append((weight, section_id, body))
    ranked.sort(reverse=True)
    return [(section_id, body) for _, section_id, body in ranked[:CANDIDATES]]


def _tau() -> float:
    raw = os.environ.get("RETRIEVAL_SCORE_TAU")
    if raw is None or raw.strip() == "":
        return TAU
    return float(raw)


@lru_cache(maxsize=1)
def _ranker() -> Ranker:
    cache = Path.home() / ".cache" / "flashrank"
    cache.mkdir(parents=True, exist_ok=True)
    return Ranker(model_name=MODEL, cache_dir=str(cache))


def _abstain() -> Draft:
    return Draft("abstain", ABSTAIN_TEXT, (), {})
