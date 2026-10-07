from pathlib import Path

from evals.judge import final_answer_correct, grader_messages, score_examples


def test_the_quiz_judge_does_not_score_without_a_key_or_touch_calibration(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    calibration = Path("results/judge_calibration.md").read_text()
    messages = grader_messages("How long is the apparel window?", "30 days.", "14 days.")
    assert messages[0]["content"].startswith("You are a teacher grading a quiz.")
    assert "factual accuracy" in messages[0]["content"]
    assert "STUDENT RESPONSE: 14 days." in messages[1]["content"]

    assert final_answer_correct(
        {"question": "How long?"},
        {"response": "14 days."},
        {"response": "30 days."},
    ) is None

    seen = {}

    def grade(question: str, reference: str, response: str) -> bool:
        seen["question"] = question
        return response == reference

    assert final_answer_correct(
        {"question": "How long?"},
        {"response": "30 days."},
        {"response": "30 days."},
        grade=grade,
    ) is True
    assert seen["question"] == "How long?"

    rows = score_examples(
        [
            {
                "id": "held-out",
                "split": "test",
                "question": "How long?",
                "response": "30 days.",
                "reference": "30 days.",
            }
        ],
        grade=grade,
        calibration=calibration,
    )
    assert rows == [{"id": "held-out", "is_correct": None}]
    assert Path("results/judge_calibration.md").read_text() == calibration
    assert "Judges have not been run." in calibration
