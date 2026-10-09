"""The LangSmith dataset rows, evaluators, and experiment runs, checked without a network call."""

import ast
import uuid
from datetime import datetime, timezone

import langsmith
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langsmith import Client, schemas

from evals import experiments
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
    reference,
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


class FakeDesk:
    """v1 without the app: a scripted LangChain model gives one Spanish reply with a photo line."""

    def __call__(self, inputs: dict) -> dict:
        model = FakeListChatModel(responses=["Tienes 30 días. Photo: visible damage."])
        reply = model.invoke(inputs["question"]).content
        return {"decision": "answer", "citations": ["REF-CATEGORY"], "response": reply, "status": "Open"}

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
    report = run(client, "dev", judge=False, upload=False)
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
    report = run(client, "dev", judge=False, router=True)
    assert client.experiments[-1]["experiment_prefix"] == "northstar-router"
    assert "### router: `fake`" in report


def test_the_command_line_defaults_to_one_repetition_without_the_router(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(langsmith, "Client", Recorder)
    monkeypatch.setattr(experiments, "run", lambda *args, **kwargs: calls.append((args[1:], kwargs)) or "report\n")
    monkeypatch.chdir(tmp_path)  # a local check writes no results file; a write here would fail
    experiments.main(["run", "--split", "dev", "--no-upload"])
    experiments.main(["run", "--split", "test", "--repetitions", "3", "--router", "--no-upload"])
    assert calls[0] == (("dev", 1, "slice1"), {"judge": True, "version": None, "upload": False, "router": False})
    assert calls[1] == (("test", 3, "slice1"), {"judge": True, "version": None, "upload": False, "router": True})
    assert not (tmp_path / "results").exists()
