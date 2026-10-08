from evals.handbook_v0 import score


def test_v0_handbook_scores_are_recorded_against_the_handbook():
    rows = {row["id"]: row for row in score()}
    assert set(rows) == {"apparel-window", "fourteen-day-trap", "out-of-handbook"}
    assert rows["out-of-handbook"]["decision"] == "abstain"
    assert rows["out-of-handbook"]["passed"] is True
    assert "REF-CATEGORY" in rows["apparel-window"]["citations"]
