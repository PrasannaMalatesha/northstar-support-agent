"""Rerank handbook sections.

ponytail: overlap picks the 20 candidates when PINECONE_API_KEY is unset
or during pytest. Otherwise Pinecone returns the 20. FlashRank stays.
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
INDEX = "northstar-handbook"
NAMESPACE = "handbook-dev"
_NAMESPACES = {
    "local": "handbook-dev",
    "dev": "handbook-dev",
    "uat": "handbook-uat",
    "prod": "handbook-prod",
}
DIMENSION = 1536
EMBEDDING_MODEL = "models/gemini-embedding-001"
# Lowest gold score on train_judge and dev is 0.41 (FAQ-HOURS).
# The 14-day trap's next section is 0.15. Abstain scores 0.
TAU = 0.2


def retrieved_answer(question: str, directory: Path | None = None) -> Draft:
    directory = directory or policy_dir()
    sections = _sections(directory)
    picked = _candidates(question, sections)
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
        weak = tuple((str(row["id"]), round(float(row["score"]), 3)) for row in results[:KEEP])
        return Draft("abstain", ABSTAIN_TEXT, (), {}, retrieved=weak)

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
    first = str(picked[0][0])
    unsure = (first,) if _vector_search() and first not in citations and _rule(bodies[first]) else ()
    return Draft("answer", "\n".join(lines), tuple(citations), match, unsure=unsure)


def _vector_search() -> bool:
    """Candidates come from Pinecone, ranked by similarity. Tests and keyless runs use word overlap."""
    return not os.environ.get("PYTEST_CURRENT_TEST") and bool(os.environ.get("PINECONE_API_KEY"))


def _candidates(question: str, sections: list[tuple[str, str]]) -> list[tuple[str, str]]:
    if not _vector_search():
        return _overlap(question, sections)
    return _pinecone_top(question)


def _pinecone_top(question: str) -> list[tuple[str, str]]:
    from langchain_pinecone import PineconeVectorStore

    store = PineconeVectorStore(
        index=_index(),
        embedding=_embeddings(),
        namespace=_namespace(),
    )
    docs = store.similarity_search(question, k=CANDIDATES)
    return [(str(doc.metadata["section_id"]), doc.page_content) for doc in docs]


def ingest_handbook(directory: Path | None = None) -> int:
    import time

    from langchain_pinecone import PineconeVectorStore
    from pinecone import Pinecone, ServerlessSpec

    directory = directory or policy_dir()
    sections = _sections(directory)
    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    name = os.environ.get("PINECONE_INDEX") or INDEX
    if name not in [item.name for item in pc.list_indexes()]:
        pc.create_index(
            name=name,
            dimension=DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
    for _ in range(30):
        if pc.describe_index(name).status.ready:
            break
        time.sleep(2)
    namespace = _namespace()
    store = PineconeVectorStore(index=pc.Index(name), embedding=_embeddings(), namespace=namespace)
    store.add_texts(
        texts=[body for _, body in sections],
        metadatas=[{"section_id": section_id} for section_id, _ in sections],
        ids=[section_id for section_id, _ in sections],
        namespace=namespace,
    )
    return len(sections)


def namespace_for(env: str | None, requested: str | None) -> str:
    """One environment, one handbook namespace. A mismatch is refused."""
    name = (env or "local").strip().lower()
    allowed = _NAMESPACES.get(name)
    if allowed is None:
        raise RuntimeError(f"Unknown environment {name}.")
    if requested and requested != allowed:
        raise RuntimeError(f"{name} may only use {allowed}.")
    return allowed


def _namespace() -> str:
    return namespace_for(os.environ.get("NORTHSTAR_ENV"), os.environ.get("PINECONE_NAMESPACE"))


def _index():
    from pinecone import Pinecone

    name = os.environ.get("PINECONE_INDEX") or INDEX
    return Pinecone(api_key=os.environ["PINECONE_API_KEY"]).Index(name)


def _embeddings():
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    inner = GoogleGenerativeAIEmbeddings(
        model=EMBEDDING_MODEL,
        google_api_key=os.environ["GOOGLE_API_KEY"],
        output_dimensionality=DIMENSION,
    )

    class _Unit:
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [_unit(vector) for vector in inner.embed_documents(texts)]

        def embed_query(self, text: str) -> list[float]:
            return _unit(inner.embed_query(text))

    return _Unit()


def _unit(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(item * item for item in vector)) or 1.0
    return [item / norm for item in vector]


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
