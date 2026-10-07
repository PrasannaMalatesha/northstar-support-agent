import re
from pathlib import Path

import pytest
from evals.handbook_v0 import score
from evals.labeled import score_handbook

from northstar.retrieve import namespace_for, retrieved_answer


def test_reranked_retrieval_matches_the_handbook_labels(monkeypatch):
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "yes")
    monkeypatch.setenv("PINECONE_API_KEY", "present")
    missed = [row["id"] for row in score_handbook(retrieved_answer) if not row["passed"]]
    assert missed == []
    rows = {row["id"]: row for row in score(retrieved_answer)}
    assert rows["out-of-handbook"]["decision"] == "abstain"
    assert rows["out-of-handbook"]["passed"] is True
    assert "REF-CATEGORY" in rows["apparel-window"]["citations"]
    assert len(rows["apparel-window"]["citations"]) <= 4


def test_dev_cannot_read_another_environments_handbook():
    assert namespace_for("dev", None) == "handbook-dev"
    assert namespace_for("local", "handbook-dev") == "handbook-dev"
    assert namespace_for("uat", "handbook-uat") == "handbook-uat"
    assert namespace_for("prod", "handbook-prod") == "handbook-prod"
    with pytest.raises(RuntimeError):
        namespace_for("dev", "handbook-prod")
    with pytest.raises(RuntimeError):
        namespace_for("dev", "handbook-uat")
    with pytest.raises(RuntimeError):
        namespace_for("uat", "handbook-dev")


def test_the_console_calls_only_its_configured_api():
    root = Path("apps/web")
    calls = []
    for path in root.rglob("*"):
        if path.suffix not in {".ts", ".tsx"} or "node_modules" in path.parts:
            continue
        if path.name == "playwright.config.ts":
            continue
        for match in re.finditer(r"fetch\(\s*(\"[^\"]+\"|`[^`]+`)", path.read_text()):
            calls.append((path.name, match.group(1)))
    assert calls
    for name, target in calls:
        relative = target.startswith('"/')
        configured = target.startswith("`${apiUrl}")
        assert relative or configured, (name, target)
