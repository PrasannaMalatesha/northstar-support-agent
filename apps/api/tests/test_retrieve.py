from evals.handbook_v0 import score
from evals.labeled import score_handbook

from northstar.retrieve import retrieved_answer


def test_reranked_retrieval_matches_the_handbook_labels():
    missed = [row["id"] for row in score_handbook(retrieved_answer) if not row["passed"]]
    assert missed == []
    rows = {row["id"]: row for row in score(retrieved_answer)}
    assert rows["out-of-handbook"]["decision"] == "abstain"
    assert rows["out-of-handbook"]["passed"] is True
    assert "REF-CATEGORY" in rows["apparel-window"]["citations"]
    assert len(rows["apparel-window"]["citations"]) <= 4
