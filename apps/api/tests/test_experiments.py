"""The LangSmith dataset rows, evaluators, and experiment runs, checked without a network call."""

import ast
import json
import subprocess
import uuid
from datetime import datetime, timezone

import langsmith
import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langsmith import Client, schemas

from evals import experiments, release_bar
from evals.experiments import (
    E2E_EVALUATORS,
    INTENT_CASES,
    _example_id,
    answer_correct,
    code_scores,
    correct,
    e2e_example,
    intent_example,
    label_match,
    measured_commit,
    reference,
    release,
    route,
    run,
    status_correct,
    v0,
)
from evals.labeled import CASES, PHOTO_CASES, SLICE2_CASES, SPANISH_CASES


def test_every_case_becomes_one_example_with_a_stable_id():
    rows = [e2e_example(case, "slice1") for case in CASES] + [e2e_example(case, "slice2") for case in SLICE2_CASES]
    assert len({row["id"] for row in rows}) == len(CASES) + len(SLICE2_CASES)
    assert _example_id("apparel-window") == e2e_example(CASES[0], "slice1")["id"]
    assert {row["split"] for row in rows} == {"train_judge", "dev", "test"}


def test_the_judge_reference_is_the_gold_rule_or_the_abstain_text():
    by_id = {case["id"]: case for case in CASES}
    assert "30 days" in reference(by_id["apparel-window"])
    assert "(REF-CATEGORY)" in reference(by_id["apparel-window"])
    assert reference(by_id["favorite-color"]).startswith("No handbook section covers that.")
    assert e2e_example(by_id["chargeback"], "slice1")["outputs"]["response"] == ""


def test_label_match_needs_the_decision_the_sections_and_the_phrases():
    trap = e2e_example({case["id"]: case for case in CASES}["fourteen-day-trap"], "slice1")["outputs"]
    good = {"decision": "answer", "citations": ["REF-CATEGORY"], "response": "30 days from delivery."}
    assert label_match({}, good, trap)["score"] == 1
    assert label_match({}, {**good, "response": "14 days, then 30 days."}, trap)["score"] == 0
    assert label_match({}, {**good, "citations": []}, trap)["score"] == 0


def test_v0_is_scored_and_status_is_skipped_for_it():
    outputs = v0({"question": "What is your favorite color?"})
    assert outputs["decision"] == "abstain"
    assert status_correct({}, outputs, {"status": "Open"})["score"] is None


def test_the_router_rows_carry_hand_labels_and_the_latest_message_decides():
    assert len({case["id"] for case in INTENT_CASES}) == len(INTENT_CASES)
    for case in INTENT_CASES:
        example = intent_example(case)
        assert correct(example["inputs"], route(example["inputs"]), example["outputs"]), case["id"]


CODE_SCORES = ["label_match", "citation_valid", "status_correct", "reply_language", "photo_verdict"]


FAKE_TOKENS = 120


class FakeDesk:
    """v1 without the app: a scripted LangChain model gives one Spanish reply with a photo line.

    The model reports its usage like a real one, and the turn is metered like the real desk's.
    """

    def __call__(self, inputs: dict) -> dict:
        usage = {"input_tokens": 100, "output_tokens": 20, "total_tokens": FAKE_TOKENS}
        reply = AIMessage("Tienes 30 días. Photo: visible damage.", usage_metadata=usage, response_metadata={"model_name": "fake"})
        with experiments._meter() as used:
            text = GenericFakeChatModel(messages=iter([reply])).invoke(inputs["question"]).content
        return {"decision": "answer", "citations": ["REF-CATEGORY"], "response": text, "status": "Open", "ticket": False, **used}

    def close(self) -> None:
        pass


class Results(list):
    experiment_name = "fake"


class Recorder:
    """A LangSmith client that records each experiment instead of running it."""

    def __init__(self) -> None:
        self.experiments: list[dict] = []

    def list_examples(self, **kwargs) -> list:
        return []

    def evaluate(self, target, **kwargs) -> Results:
        self.experiments.append(kwargs)
        return Results()


class OfflineClient(Client):
    """The real LangSmith runner with no server behind it. Every request is recorded and fails."""

    def __init__(self, examples: list) -> None:
        super().__init__(api_url="http://127.0.0.1:9", api_key="offline", auto_batch_tracing=False)
        self.examples = examples
        self.sent: list[tuple[str, str]] = []

        def refuse(method, url, *args, **kwargs):
            self.sent.append((method, url))
            raise ConnectionError("offline")

        self.session.request = refuse

    def list_examples(self, **kwargs) -> list:
        return self.examples


def _example(row: dict) -> schemas.Example:
    return schemas.Example(
        id=uuid.UUID(row["id"]),
        dataset_id=uuid.uuid4(),
        inputs=row["inputs"],
        outputs=row["outputs"],
        metadata=row["metadata"],
        created_at=datetime.now(timezone.utc),
    )


def _means(report: str, version: str) -> dict:
    section = report.split(f"### {version}:")[1]
    return ast.literal_eval(section.split("Mean scores: ")[1].splitlines()[0])


def test_one_evaluator_returns_every_code_score_by_name():
    assert E2E_EVALUATORS == [code_scores, answer_correct]
    row = e2e_example(PHOTO_CASES[0], "slice3-photo")["outputs"]
    outputs = {"decision": "approve_refund", "citations": ["REF-DAMAGED"], "response": "Photo: visible damage.", "status": "Waiting for approval"}
    scores = code_scores({}, outputs, row)
    assert [score["key"] for score in scores] == CODE_SCORES
    assert {score["key"]: score["score"] for score in scores} == {
        "label_match": 1,
        "citation_valid": 1,
        "status_correct": 1,
        "reply_language": None,
        "photo_verdict": 1,
    }


def test_a_local_run_sends_nothing_and_reports_the_same_score_names(monkeypatch):
    monkeypatch.setattr(experiments, "Desk", FakeDesk)
    rows = [e2e_example(CASES[0], "slice1"), e2e_example(SPANISH_CASES[0], "slice3-es"), e2e_example(PHOTO_CASES[0], "slice3-photo")]
    client = OfflineClient([_example(row) for row in rows])
    report, _ = run(client, "dev", judge=False, upload=False)
    assert client.sent == []
    assert "3 cases, 1 repetition(s), code checks only, no judge, not uploaded" in report
    assert sorted(_means(report, "v1")) == sorted(CODE_SCORES)
    assert _means(report, "v1")["reply_language"] == 1.0
    assert "router" not in report


def test_repetitions_default_to_one_and_three_stay_for_the_release_run(monkeypatch):
    monkeypatch.setattr(experiments, "Desk", FakeDesk)
    client = Recorder()
    run(client, "dev", judge=False)
    assert [experiment["num_repetitions"] for experiment in client.experiments] == [1, 1]
    client = Recorder()
    run(client, "dev", repetitions=3, judge=False)
    assert [experiment["num_repetitions"] for experiment in client.experiments] == [3, 3]


def test_a_run_uploads_unless_told_not_to(monkeypatch):
    monkeypatch.setattr(experiments, "Desk", FakeDesk)
    client = Recorder()
    run(client, "dev", judge=False)
    assert [experiment["upload_results"] for experiment in client.experiments] == [True, True]
    client = Recorder()
    run(client, "dev", judge=False, upload=False, router=True)
    assert [experiment["upload_results"] for experiment in client.experiments] == [False, False, False]
    assert all(experiment["disable_evaluator_tracing"] for experiment in client.experiments)


def test_the_router_experiment_runs_only_when_asked(monkeypatch):
    monkeypatch.setattr(experiments, "Desk", FakeDesk)
    client = Recorder()
    run(client, "dev", judge=False)
    assert [experiment["experiment_prefix"] for experiment in client.experiments] == ["northstar-v0-dev", "northstar-v1-dev"]
    client = Recorder()
    report, _ = run(client, "dev", judge=False, router=True)
    assert client.experiments[-1]["experiment_prefix"] == "northstar-router"
    assert "### router: `fake`" in report


def test_the_command_line_defaults_to_one_repetition_without_the_router(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(langsmith, "Client", Recorder)
    monkeypatch.setattr(experiments, "run", lambda *args, **kwargs: calls.append((args[1:], kwargs)) or ("report\n", []))
    monkeypatch.chdir(tmp_path)  # a local check writes no results file; a write here would fail
    experiments.main(["run", "--split", "dev", "--no-upload"])
    experiments.main(["run", "--split", "test", "--repetitions", "3", "--router", "--no-upload"])
    assert calls[0] == (("dev", 1, "slice1"), {"judge": True, "version": None, "upload": False, "router": False})
    assert calls[1] == (("test", 3, "slice1"), {"judge": True, "version": None, "upload": False, "router": True})
    assert not (tmp_path / "results").exists()


def test_each_row_records_its_seconds_and_the_tokens_its_models_reported(monkeypatch):
    monkeypatch.setattr(experiments, "Desk", FakeDesk)
    rows = [e2e_example(CASES[0], "slice1"), e2e_example(SPANISH_CASES[0], "slice3-es")]
    client = OfflineClient([_example(row) for row in rows])
    _, gate_rows = run(client, "dev", judge=False, upload=False)
    # The release bar reads the live desk's rows only, v0 is a baseline.
    assert [row["language"] for row in gate_rows] == ["en", "es"]
    assert all(row["tokens"] == FAKE_TOKENS and 0 <= row["seconds"] < 5 for row in gate_rows)
    assert gate_rows[0]["passed"] is True and gate_rows[0]["ticket"] is False
    # v0 is metered too. Its handbook answer calls no chat model.
    outputs = v0({"question": "What is your favorite color?"})
    assert outputs["tokens"] == 0 and outputs["seconds"] >= 0


def test_the_release_run_adds_the_spanish_turns_and_records_the_gates(monkeypatch):
    monkeypatch.setattr(experiments, "Desk", FakeDesk)
    test_case = next(case for case in CASES if case["split"] == "test" and case["decision"] == "answer")
    rows = [e2e_example(test_case, "slice1"), e2e_example(SPANISH_CASES[0], "slice3-es")]
    client = OfflineClient([_example(row) for row in rows])
    commit = "c" * 40
    report, bar = release(client, commit, judge=False, upload=False)
    assert client.sent == []
    assert bar["commit"] == commit and bar["uploaded"] is False
    # The offline client returns both rows for test, so v1 ran 2 cases and the Spanish turns 1, three times each.
    assert bar["rows"] == 3 * 2 + 3 * 1
    assert set(bar["gates"]) == set(release_bar.GATES)
    assert bar["measured"]["max_tokens"] == FAKE_TOKENS
    assert bar["measured"]["p95_seconds_es"] is not None
    assert "3 repetition(s)" in report and "### v1 Spanish turns:" in report


def test_the_release_command_writes_the_results_file(monkeypatch, tmp_path):
    calls = []
    bar = {"commit": "d" * 40, "gates": {"latency": True}}
    monkeypatch.setattr(langsmith, "Client", Recorder)
    monkeypatch.setattr(experiments, "measured_commit", lambda: "d" * 40)
    monkeypatch.setattr(experiments, "release", lambda *args, **kwargs: calls.append((args[1:], kwargs)) or ("report", bar))
    monkeypatch.chdir(tmp_path)
    (tmp_path / "results").mkdir()
    experiments.main(["release", "--no-upload"])
    assert calls == [(("d" * 40, "slice1"), {"judge": True, "upload": False})]
    assert json.loads((tmp_path / "results/release_bar.json").read_text()) == bar
    assert not (tmp_path / "results/langsmith_test.md").exists()


def _git(repo, *args: str) -> str:
    quiet = ["-c", "user.name=test", "-c", "user.email=test@example.com", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null"]
    return subprocess.run(["git", *quiet, *args], cwd=repo, check=True, capture_output=True, text=True).stdout


def test_a_release_run_names_its_commit_and_refuses_uncommitted_code(monkeypatch, tmp_path):
    _git(tmp_path, "init", "-q")
    (tmp_path / "results").mkdir()
    (tmp_path / "app.py").write_text("one\n")
    (tmp_path / "results/old.md").write_text("old\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "First.")
    monkeypatch.chdir(tmp_path)
    head = _git(tmp_path, "rev-parse", "HEAD").strip()
    (tmp_path / "results/old.md").write_text("new\n")  # an earlier results file is not code
    assert measured_commit() == head
    (tmp_path / "app.py").write_text("two\n")
    with pytest.raises(SystemExit, match="app.py"):
        measured_commit()
