"""The golden dataset and the experiments in Langfuse, beside the LangSmith runner in evals.experiments.

    uv run python -m evals.langfuse_experiments sync
    uv run python -m evals.langfuse_experiments run --split test            # v0 and v1, code checks and the judge
    uv run python -m evals.langfuse_experiments run --split dev --version slice3-photo --no-judge
    uv run python -m evals.langfuse_experiments run --split test --router   # also the intent router
    uv run python -m evals.langfuse_experiments release                     # writes results/release_bar.json
    uv run python -m evals.langfuse_experiments promote <trace_id> --decision answer --sections REF-GIFT

Only the platform differs from evals.experiments: the same labeled cases, the same targets (v0, the live desk
v1, the router, the customer chat), the same evaluators, and the same release bar. One dataset item per case,
with a stable id, so a second sync adds nothing twice. Each experiment item is a trace linked to its dataset
run, and the desk turn's full trace (agent steps, tools, generations) nests under it.

Versions follow the LangSmith tags: an item's metadata names the version that added it, and --tag X selects
every version up to X. A promoted specialist edit is a new version, "edit-<UTC time>".

Trace budget: a desk item is about 20 units (the item, the turn's ~12 observations, its scores), a v0 or router
item about 8. A release run is about 1,600 of the free plan's 50,000 a month. Runs default to one repetition.
https://langfuse.com/docs/evaluation/experiments/experiments-via-sdk
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from evals.labeled import CASES, HANDOVER_CASES, INTENT_CASES, ONLINE_CASES, ONLINE_VERSION, PHOTO_CASES, SLICE2_CASES, SPANISH_CASES

E2E = "northstar-e2e"
INTENT = "northstar-intent"
# The order versions were added in. Promoted edits ("edit-<UTC time>") come after, in time order.
VERSIONS = ("slice1", "slice2", "slice3-es", "slice3-photo", "update-handover", ONLINE_VERSION)
RELEASE_FILE = Path("results/release_bar.json")


def _client():
    from northstar import langfuse_tracing

    if not langfuse_tracing.enabled():
        raise SystemExit("set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY in .env first")
    return langfuse_tracing.client()


def _item(example: dict) -> dict:
    """A LangSmith-shaped example (evals.experiments.e2e_example) as a Langfuse dataset item."""
    return {
        "id": example["id"],
        "input": example["inputs"],
        "expected_output": example.get("outputs"),
        "metadata": {**example.get("metadata", {}), "split": example.get("split", "dev")},
    }


def _existing_ids(langfuse, dataset: str) -> set[str]:
    ids, page = set(), 1
    while True:
        batch = langfuse.api.dataset_items.list(dataset_name=dataset, page=page, limit=100)
        ids |= {item.id for item in batch.data}
        if page >= batch.meta.total_pages:
            return ids
        page += 1


def _add(langfuse, dataset: str, description: str, items: list[dict]) -> int:
    try:
        langfuse.get_dataset(dataset)
    except Exception:
        langfuse.create_dataset(name=dataset, description=description)
    have = _existing_ids(langfuse, dataset)
    new = [item for item in items if item["id"] not in have]
    for item in new:
        langfuse.create_dataset_item(dataset_name=dataset, **item)
    return len(new)


def sync(langfuse) -> str:
    from evals.experiments import e2e_example, intent_example

    about = "Northstar golden cases. Splits train_judge, dev, test are frozen at first use."
    by_version = {
        "slice1": CASES,
        "slice2": SLICE2_CASES,
        "slice3-es": SPANISH_CASES,
        "slice3-photo": PHOTO_CASES,
        "update-handover": HANDOVER_CASES,
        ONLINE_VERSION: ONLINE_CASES,
    }
    added = sum(_add(langfuse, E2E, about, [_item(e2e_example(case, version)) for case in cases]) for version, cases in by_version.items())
    routes = _add(langfuse, INTENT, "Hand-labeled routes. The latest user message decides.", [_item(intent_example(case)) for case in INTENT_CASES])
    langfuse.flush()
    return f"{E2E}: {added} added. {INTENT}: {routes} added."


def _versions_up_to(tag: str, seen: set[str]) -> set[str]:
    ordered = list(VERSIONS) + sorted(version for version in seen if version.startswith("edit-"))
    if tag not in ordered:
        raise SystemExit(f"unknown tag {tag}; known: {ordered}")
    return set(ordered[: ordered.index(tag) + 1])


def items(langfuse, dataset: str, split: str | None = None, tag: str | None = None, version: str | None = None) -> list:
    """The dataset's active items, by split, up to a version tag, or of one version only."""
    rows = [item for item in langfuse.get_dataset(dataset).items if str(getattr(item, "status", "ACTIVE")).upper().endswith("ACTIVE")]
    meta = lambda item: item.metadata or {}  # noqa: E731
    if split:
        rows = [item for item in rows if meta(item).get("split") == split]
    if tag:
        allowed = _versions_up_to(tag, {meta(item).get("version", "") for item in rows})
        rows = [item for item in rows if meta(item).get("version") in allowed]
    if version:
        rows = [item for item in rows if meta(item).get("version") == version]
    return sorted(rows, key=lambda item: meta(item).get("case_id", ""))


def _evaluator(check):
    """One of evals.experiments' evaluators, in Langfuse's evaluator shape. A score of None is skipped."""
    from langfuse import Evaluation

    def evaluate(*, input, output, expected_output, metadata=None, **_kwargs):
        result = check(input, output, expected_output)
        if isinstance(result, bool):  # the router's correct()
            result = {"key": check.__name__, "score": int(result)}
        results = result if isinstance(result, list) else [result]
        return [
            Evaluation(name=row["key"], value=float(row["score"]), comment=row.get("comment"))
            for row in results
            if row.get("score") is not None
        ]

    evaluate.__name__ = check.__name__
    return evaluate


def _task(target):
    from northstar import langfuse_tracing

    def task(*, item, **_kwargs):
        with langfuse_tracing.nested_under_current():
            return target(item.input if hasattr(item, "input") else item["input"])

    return task


def _experiment(langfuse, name: str, data: list, target, checks, repetitions: int, concurrency: int, metadata: dict) -> list:
    """Every repetition of one experiment. Returns the item results of all of them."""
    results = []
    for repetition in range(1, repetitions + 1):
        run = langfuse.run_experiment(
            name=name,
            run_name=f"{name} {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} #{repetition}",
            data=data,
            task=_task(target),
            evaluators=[_evaluator(check) for check in checks],
            max_concurrency=concurrency,
            metadata={key: str(value) for key, value in metadata.items()},
        )
        print(f"{name} #{repetition}: {run.dataset_run_url or run.run_name}", flush=True)
        results += run.item_results
    return results


def _scores(result) -> dict:
    return {evaluation.name: evaluation.value for evaluation in result.evaluations}


def _section(name: str, results: list) -> list[str]:
    totals: dict[str, list[float]] = {}
    misses = set()
    for result in results:
        case = (result.item.metadata or {}).get("case_id", "?") if hasattr(result.item, "metadata") else "?"
        for evaluation in result.evaluations:
            totals.setdefault(evaluation.name, []).append(float(evaluation.value))
            if evaluation.value == 0:
                misses.add(f"{case}: {evaluation.name} ({evaluation.comment or 'no comment'})")
    means = {key: round(sum(values) / len(values), 3) for key, values in sorted(totals.items())}
    return [f"### {name}", "", f"Mean scores: {means}", "", "Misses:", *([f"- {miss}" for miss in sorted(misses)] or ["- none"]), ""]


def run(langfuse, split: str, repetitions: int = 1, tag: str = "slice1", judge: bool = True, version: str | None = None, router: bool = False):
    """v0 and the live desk on one split. Returns the report and the desk's rows for the release bar."""
    from evals.experiments import E2E_EVALUATORS, Desk, answer_correct, correct, gate_fields, route, v0
    from evals.judge import judges_may_score_test

    if judge and split == "test" and not judges_may_score_test(Path("results/judge_calibration.md").read_text()):
        raise SystemExit("the judge is not calibrated for the test split")
    data = items(langfuse, E2E, split=split, tag=tag, version=version)
    checks = E2E_EVALUATORS if judge else [check for check in E2E_EVALUATORS if check is not answer_correct]
    lines = [f"## {split} split, tag {tag}, {len(data)} cases, {repetitions} repetition(s), {'with' if judge else 'without'} the quiz judge (Langfuse)", ""]
    rows: list[dict] = []
    desk = Desk()
    try:
        for name, target, concurrency in (("v0", v0, 4), ("v1", desk, 1)):
            results = _experiment(langfuse, f"northstar-{name}-{split}", data, target, checks, repetitions, concurrency, {"version": name, "split": split, "tag": tag})
            lines += _section(name, results)
            if target is desk:
                rows += [gate_fields(result.output, result.item.expected_output, _scores(result)) for result in results]
    finally:
        desk.close()
    if router:
        routed = _experiment(langfuse, "northstar-router", items(langfuse, INTENT), route, [correct], 1, 4, {"version": "router"})
        lines += _section("router", routed)
    langfuse.flush()
    return "\n".join(lines), rows


def release(langfuse, commit: str, tag: str = "slice1", judge: bool = True) -> tuple[str, dict]:
    """The release bar from Langfuse runs: the test split with three repetitions, then the Spanish turns."""
    from evals.experiments import RELEASE_REPETITIONS, Desk, code_scores, gate_fields
    from evals.release_bar import record

    report, rows = run(langfuse, "test", RELEASE_REPETITIONS, tag, judge=judge)
    spanish = items(langfuse, E2E, split="dev", version="slice3-es")
    desk = Desk()
    try:
        results = _experiment(langfuse, "northstar-v1-es-dev", spanish, desk, [code_scores], RELEASE_REPETITIONS, 1, {"version": "v1", "split": "dev", "tag": "slice3-es"})
    finally:
        desk.close()
    rows += [gate_fields(result.output, result.item.expected_output, _scores(result)) for result in results]
    bar = {**record(rows, commit), "uploaded": True, "platform": "langfuse"}
    lines = [report, f"## Release bar on {commit}", "", *_section("v1 Spanish turns", results), f"Gates: {bar['gates']}", "", f"Measured: {bar['measured']}", ""]
    langfuse.flush()
    return "\n".join(lines), bar


def promote(langfuse, trace_id: str, decision: str, sections: list[str], split: str, status: str | None) -> str:
    """A specialist's edit on a traced turn becomes a golden case under a new version.

    The question is the turn's root input (already masked). The corrected text is the specialist_edit score.
    Nothing here changes the handbook or a rule."""
    from evals.experiments import _example_id
    from evals.labeled import registry_ids

    unknown = [section for section in sections if section not in registry_ids()]
    if unknown:
        raise SystemExit(f"unknown sections {unknown}")
    # The comment is in the "details" field group; the default list leaves it out.
    edits = langfuse.api.scores_v3.get_many_v3(trace_id=trace_id, name="specialist_edit", fields="core,details").data
    comment = next((getattr(score, "comment", None) for score in edits if getattr(score, "comment", None)), None)
    if not comment or "After:" not in comment:
        raise SystemExit("that trace has no specialist edit")
    roots = langfuse.api.observations.get_many(trace_id=trace_id, is_root_observation=True, fields="core,io", limit=1).data
    root = roots[0] if roots else None
    root_input = (root if isinstance(root, dict) else root.dict()).get("input") if root else None
    question = (json.loads(root_input) if isinstance(root_input, str) else root_input or {}).get("question")
    if not question:
        raise SystemExit("that trace has no question on its root")
    case_id = f"edit-{trace_id[:8]}"
    version = f"edit-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"
    item = {
        "id": _example_id(case_id),
        "input": {"question": question, "customer": None, "advance_days": 0},
        "expected_output": {
            "decision": decision,
            "sections": sections,
            "status": status,
            "response": comment.split("After:", 1)[1].strip(),
            "text_includes": [],
            "text_excludes": [],
        },
        "metadata": {"case_id": case_id, "channel": "desk" if status else "handbook", "version": version, "split": split},
        "source_trace_id": trace_id,
    }
    added = _add(langfuse, E2E, "", [item])
    langfuse.flush()
    return f"{case_id} added under version {version}" if added else f"{case_id} is already in the dataset"


def main(argv: list[str] | None = None) -> None:
    root = Path(__file__).resolve().parents[1]
    sys.path[:0] = [str(root / "apps/api"), str(root / "apps/api/tests")]
    from northstar.agent_model import _load_local_env

    _load_local_env()
    parser = argparse.ArgumentParser(prog="evals.langfuse_experiments")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("sync")
    ran = commands.add_parser("run")
    ran.add_argument("--split", default="test", choices=("train_judge", "dev", "test"))
    ran.add_argument("--repetitions", type=int, default=1)
    ran.add_argument("--tag", default="slice1")
    ran.add_argument("--no-judge", action="store_true")
    ran.add_argument("--version")
    ran.add_argument("--router", action="store_true")
    released = commands.add_parser("release")
    released.add_argument("--tag", default="slice1")
    released.add_argument("--no-judge", action="store_true")
    promoted = commands.add_parser("promote")
    promoted.add_argument("trace_id")
    promoted.add_argument("--decision", required=True)
    promoted.add_argument("--sections", default="")
    promoted.add_argument("--split", default="dev", choices=("dev", "test"))
    promoted.add_argument("--status")
    args = parser.parse_args(argv)

    langfuse = _client()
    if args.command == "sync":
        print(sync(langfuse))
    elif args.command == "run":
        report, _rows = run(langfuse, args.split, args.repetitions, args.tag, judge=not args.no_judge, version=args.version, router=args.router)
        print(report)
    elif args.command == "release":
        from evals.experiments import measured_commit

        commit = measured_commit()
        report, bar = release(langfuse, commit, args.tag, judge=not args.no_judge)
        print(report)
        RELEASE_FILE.write_text(json.dumps(bar, indent=2) + "\n")
        print(f"{RELEASE_FILE}: {'passed' if all(bar['gates'].values()) else 'FAILED'}. Commit it, then open the PR into uat.")
    elif args.command == "promote":
        sections = [section.strip() for section in args.sections.split(",") if section.strip()]
        print(promote(langfuse, args.trace_id, args.decision, sections, args.split, args.status))


if __name__ == "__main__":
    main()
