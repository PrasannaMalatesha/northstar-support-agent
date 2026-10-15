"""The Langfuse runner reuses the LangSmith runner's cases, targets, and evaluators; only the platform differs."""

from types import SimpleNamespace

from evals import langfuse_experiments as lx


def test_an_evaluator_keeps_every_score_name_and_skips_scores_that_do_not_apply():
    def code(inputs, outputs, reference):
        return [{"key": "label_match", "score": 1, "comment": "ok"}, {"key": "status_correct", "score": None}]

    def correct(inputs, outputs, reference):
        return False

    scored = lx._evaluator(code)(input={}, output={}, expected_output={}, metadata={})
    assert [(e.name, e.value, e.comment) for e in scored] == [("label_match", 1.0, "ok")]
    assert [(e.name, e.value) for e in lx._evaluator(correct)(input={}, output={}, expected_output={})] == [("correct", 0.0)]


def test_a_tag_selects_every_version_up_to_it_and_edits_come_last_in_time_order():
    seen = {"slice1", "slice2", "edit-20261011-090000", "edit-20261010-120000"}
    assert lx._versions_up_to("slice2", seen) == {"slice1", "slice2"}
    assert lx._versions_up_to("edit-20261010-120000", seen) == set(lx.VERSIONS) | {"edit-20261010-120000"}


def test_a_case_becomes_one_dataset_item_with_its_stable_id_and_split():
    from evals.experiments import e2e_example
    from evals.labeled import CASES

    example = e2e_example(CASES[0], "slice1")
    item = lx._item(example)
    assert item["id"] == example["id"] and item["input"] == example["inputs"] and item["expected_output"] == example["outputs"]
    assert item["metadata"]["split"] == example["split"] and item["metadata"]["version"] == "slice1"


def test_items_filter_by_split_tag_and_version():
    def row(case, split, version, status="ACTIVE"):
        return SimpleNamespace(metadata={"case_id": case, "split": split, "version": version}, status=status)

    data = [row("b", "test", "slice1"), row("a", "test", "slice2"), row("c", "dev", "slice1"), row("d", "test", "slice1", "ARCHIVED")]
    langfuse = SimpleNamespace(get_dataset=lambda _name: SimpleNamespace(items=data))
    assert [i.metadata["case_id"] for i in lx.items(langfuse, "x", split="test", tag="slice1")] == ["b"]
    assert [i.metadata["case_id"] for i in lx.items(langfuse, "x", split="test", tag="slice2")] == ["a", "b"]
    assert [i.metadata["case_id"] for i in lx.items(langfuse, "x", version="slice1")] == ["b", "c"]


def test_the_runner_refuses_to_start_without_keys():
    import pytest

    with pytest.raises(SystemExit):
        lx._client()


def test_a_promoted_edit_reads_the_correction_from_the_score_s_details(monkeypatch):
    """Found on the first real promotion: the default score list has no comment, so every trace looked unedited."""
    asked, added = [], []

    def scores(**query):
        asked.append(query)
        comment = "Before:\nA cited non-answer.\n\nAfter:\nThe handbook does not say that." if "details" in (query.get("fields") or "") else None
        return SimpleNamespace(data=[SimpleNamespace(comment=comment)])

    root = {"input": '{"question": "Can someone pay with two different cards on one order?"}'}
    langfuse = SimpleNamespace(
        api=SimpleNamespace(
            scores_v3=SimpleNamespace(get_many_v3=scores),
            observations=SimpleNamespace(get_many=lambda **query: SimpleNamespace(data=[root])),
        ),
        flush=lambda: None,
    )
    monkeypatch.setattr(lx, "_add", lambda client, dataset, description, items: added.extend(items) or len(items))
    said = lx.promote(langfuse, "f4d5286f7b85c8b9", "abstain", [], "dev", None)
    assert said.startswith("edit-f4d5286f added under version edit-")
    assert asked[0]["trace_id"] == "f4d5286f7b85c8b9" and "details" in asked[0]["fields"]
    [item] = added
    assert item["input"]["question"].startswith("Can someone pay")
    assert item["expected_output"]["decision"] == "abstain" and item["expected_output"]["response"] == "The handbook does not say that."
    assert item["source_trace_id"] == "f4d5286f7b85c8b9" and item["metadata"]["split"] == "dev"
