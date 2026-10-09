"""The golden dataset and the offline experiments, in LangSmith.

    uv run python -m evals.experiments sync
    uv run python -m evals.experiments run --split dev --no-upload
    uv run python -m evals.experiments run --split test --repetitions 3
    uv run python -m evals.experiments run --split dev --tag update-handover --version update-handover --no-upload
    uv run python -m evals.experiments release
    uv run python -m evals.experiments promote <run_id> --decision answer --sections REF-CATEGORY

A run costs LangSmith traces, and the month has a fixed allowance. One repetition is the default;
three are for the release run on test. --no-upload is a local check that uploads nothing.
--router adds the router experiment, for when routing changed.

release is the run before a promotion into uat: test with three repetitions, plus the Spanish turns.
It writes results/release_bar.json with the commit it measured and each gate. CI on a PR into uat
checks that file (evals/release_check.py), so no keys go into GitHub.

An experiment is a dataset, a target, and evaluators:
https://docs.langchain.com/langsmith/evaluate-complex-agent
The targets are synchronous (v1 drives the desk through the API, one case at a time),
so this uses client.evaluate, the sync form of aevaluate. A hand-over case (issue #145) drives
the customer chat instead, and its decision is what the chat offers.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from evals.labeled import (
    CASES,
    HANDOVER_CASES,
    INTENT_CASES,
    PHOTO_CASES,
    SLICE2_CASES,
    SPANISH_CASES,
    judges_may_score_test,
    matches,
)

E2E = "Northstar Support: E2E"
INTENT = "Northstar Support: Intent Classifier"
START = datetime(2026, 10, 6, 15, 0, tzinfo=timezone.utc)
RELEASE_REPETITIONS = 3
RELEASE_FILE = Path("results/release_bar.json")


def _example_id(case_id: str) -> str:
    # Stable ids, so a second sync adds nothing twice.
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"northstar:{case_id}"))


def reference(case: dict) -> str:
    """The quiz judge's ground truth: the gold section rules, or the abstain text."""
    from northstar.handbook import ABSTAIN_TEXT, _rule, _sections, policy_dir

    if case["decision"] == "abstain":
        return ABSTAIN_TEXT
    bodies = dict(_sections(policy_dir()))
    return "\n".join(f"{_rule(bodies[section])} ({section})" for section in case["sections"])


def photo_url(name: str) -> str:
    import base64

    raw = (Path(__file__).parent / "photos" / name).read_bytes()
    return "data:image/png;base64," + base64.b64encode(raw).decode()


def e2e_example(case: dict, version: str) -> dict:
    channel = case.get("channel", "desk")
    return {
        "id": _example_id(case["id"]),
        "inputs": {
            "question": case["question"],
            "customer": case.get("customer"),
            "advance_days": case.get("advance_days", 0),
            **({"photo": photo_url(case["photo"])} if case.get("photo") else {}),
            **(
                {"channel": "chat", "order_id": case["order_id"], "earlier": list(case["earlier"]), "live": case["live"]}
                if channel == "chat"
                else {}
            ),
        },
        "outputs": {
            "decision": case["decision"],
            "sections": list(case["sections"]),
            "status": case.get("status"),
            "response": reference(case) if channel == "handbook" else "",
            "text_includes": list(case.get("text_includes", ())),
            "text_excludes": list(case.get("text_excludes", ())),
            **({"photo_verdict": case["photo_verdict"]} if case.get("photo_verdict") else {}),
            "language": case.get("language", "en"),
        },
        "metadata": {"case_id": case["id"], "channel": channel, "version": version},
        "split": case.get("split", "dev"),
    }


def intent_example(case: dict) -> dict:
    roles = ("user", "assistant")
    messages = [{"role": roles[i % 2], "content": text} for i, text in enumerate(case["messages"])]
    return {
        "id": _example_id(case["id"]),
        "inputs": {"messages": messages},
        "outputs": {"route": case["route"]},
        "metadata": {"case_id": case["id"]},
    }


def _add(client, name: str, description: str, examples: list[dict], tag: str | None = None) -> int:
    if client.has_dataset(dataset_name=name):
        dataset = client.read_dataset(dataset_name=name)
    else:
        dataset = client.create_dataset(name, description=description)
    have = {str(example.id) for example in client.list_examples(dataset_id=dataset.id)}
    new = [example for example in examples if example["id"] not in have]
    if new:
        client.create_examples(dataset_id=dataset.id, examples=new)
        if tag:
            # Tag the server's newest version. A local clock can sit just before it and miss the new rows.
            latest = next(iter(client.list_dataset_versions(dataset_id=dataset.id, limit=1)))
            client.update_dataset_tag(dataset_id=dataset.id, as_of=latest.as_of, tag=tag)
    return len(new)


def sync(client) -> None:
    about = "Northstar golden cases. Splits train_judge, dev, test are frozen at first use."
    added = _add(client, E2E, about, [e2e_example(case, "slice1") for case in CASES], "slice1")
    added += _add(client, E2E, about, [e2e_example(case, "slice2") for case in SLICE2_CASES], "slice2")
    added += _add(client, E2E, about, [e2e_example(case, "slice3-es") for case in SPANISH_CASES], "slice3-es")
    added += _add(client, E2E, about, [e2e_example(case, "slice3-photo") for case in PHOTO_CASES], "slice3-photo")
    added += _add(client, E2E, about, [e2e_example(case, "update-handover") for case in HANDOVER_CASES], "update-handover")
    routes = _add(client, INTENT, "Hand-labeled routes. The latest user message decides.", [intent_example(case) for case in INTENT_CASES])
    print(f"{E2E}: {added} added. {INTENT}: {routes} added.")


# Targets ------------------------------------------------------------------


@contextmanager
def _meter():
    """The seconds and model tokens of one turn, for the release bar's latency and token gates.

    Tokens are what the chat models report (usage_metadata), summed over every call in the turn.
    https://docs.langchain.com/oss/python/langchain/models#token-usage
    """
    from langchain_core.callbacks import get_usage_metadata_callback

    used: dict = {}
    started = time.perf_counter()
    with get_usage_metadata_callback() as usage:
        yield used
    used["seconds"] = round(time.perf_counter() - started, 3)
    used["tokens"] = sum(model["total_tokens"] for model in usage.usage_metadata.values())


def chat_turns(client, inputs: dict) -> dict:
    """A hand-over case in the customer chat (issue #145), through the chat API as a customer uses it.

    The earlier turns set the case up, and only the last turn is timed. The decision is what the chat
    offers after it: talk_to_person, leave_message, or none.
    """
    started = client.post("/chat/start", json={"order_id": inputs["order_id"], "email": inputs["customer"]})
    chat = {"Authorization": f"Bearer {started.json()['chat_token']}"}
    for earlier in inputs["earlier"]:
        client.post("/chat/messages", headers=chat, json={"question": earlier})
    with _meter() as used:
        body = client.post("/chat/messages", headers=chat, json={"question": inputs["question"]}).json()
    offer = client.get("/chat/state", headers=chat).json()["offer"]
    reply = body["messages"][-1]["text"]
    return {"decision": offer or "none", "citations": [], "response": reply, "status": None, "ticket": False, **used}


def v0(inputs: dict) -> dict:
    """v0: the handbook answerer sees every question. It does not look up an order."""
    from northstar.handbook import answer

    with _meter() as used:
        draft = answer(inputs["question"])
    return {"decision": draft.decision, "citations": list(draft.citations), "response": draft.text, "status": None, **used}


class Desk:
    """v1: the desk through the API, with the live agent model and Pinecone. One case at a time."""

    def __init__(self) -> None:
        from fastapi.testclient import TestClient
        from northstar.clock import SystemClock
        from northstar.identity.postgres import PostgresIdentityStore
        from northstar.identity.seed import seed_staff
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        from conftest import TEST_URL, _ensure_test_database
        from northstar_api.main import create_app
        from northstar_api.settings import Settings

        class Clock(SystemClock):
            moment = START

            def now(self):
                return self.moment

            def advance(self, **kwargs) -> None:
                self.moment += timedelta(**kwargs)

        from northstar import online

        # The app's sampled online judge would score experiment runs and compete for the judge model.
        online.background = lambda fn, *args, **kwargs: None
        _ensure_test_database()
        self.clock = Clock()
        self.pool = ConnectionPool(TEST_URL, min_size=1, max_size=2, kwargs={"row_factory": dict_row}, open=True)
        secret = "eval-token-secret-at-least-32-characters"
        # A hand-over case with live chat on runs on its own app, since the switch is a setting.
        apps = [
            create_app(
                settings=Settings(database_url=TEST_URL, token_secret=secret, live_agents_enabled=live),
                clock=self.clock,
                pool=self.pool,
            )
            for live in (False, True)
        ]
        PostgresIdentityStore(self.pool).truncate()
        seed_staff(PostgresIdentityStore(self.pool))
        self.client, self.live_client = (TestClient(app).__enter__() for app in apps)

    def __call__(self, inputs: dict) -> dict:
        from test_labeled_set import _clear_cases, _fresh, _login

        _clear_cases()
        self.clock.moment = START + timedelta(days=inputs.get("advance_days") or 0)
        if inputs.get("channel") == "chat":
            return chat_turns(self.live_client if inputs["live"] else self.client, inputs)
        specialist = _login(self.client, "specialist@northstar.example", "northstar-specialist")
        lead = _login(self.client, "lead@northstar.example", "northstar-lead")
        _fresh(self.client, specialist, lead, self.clock)
        if inputs.get("customer"):
            self.client.post("/cases/current/customer", headers=specialist, json={"query": inputs["customer"]})
        message = {"question": inputs["question"], **({"photo": inputs["photo"]} if inputs.get("photo") else {})}
        # Only the turn is timed. The case reset and the logins above are not part of it.
        with _meter() as used:
            body = self.client.post("/cases/current/messages", headers=specialist, json=message).json()
        draft = body["messages"][-1]
        return {
            "decision": draft["decision"],
            "citations": draft["citations"],
            "response": draft["body"],
            "status": body["status"],
            # Nothing is approved during an experiment, so any ticket is a ticket without approval.
            "ticket": body["ticket_id"] is not None,
            **used,
        }

    def close(self) -> None:
        self.client.__exit__(None, None, None)
        self.live_client.__exit__(None, None, None)
        self.pool.close()


def route(inputs: dict) -> dict:
    """The intent_classifier node alone, on the latest user message."""
    from northstar.graph import intent_classifier

    latest = [message for message in inputs["messages"] if message["role"] == "user"][-1]["content"]
    return {"route": intent_classifier({"question": latest}).goto}


# Evaluators ---------------------------------------------------------------


def label_match(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    """Decision, every gold section cited, and the required or forbidden phrases."""
    ok = matches(reference_outputs, outputs["decision"], outputs["citations"], outputs["response"])
    return {"key": "label_match", "score": int(ok), "comment": f"got {outputs['decision']}, wanted {reference_outputs['decision']}"}


def citation_valid(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    from evals.labeled import registry_ids
    from evals.release_bar import bad_citation

    return {"key": "citation_valid", "score": int(not bad_citation(outputs["citations"], registry_ids()))}


def status_correct(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    if outputs["status"] is None or reference_outputs.get("status") is None:
        return {"key": "status_correct", "score": None, "comment": "handbook row or v0: no case status"}
    return {"key": "status_correct", "score": int(outputs["status"] == reference_outputs["status"])}


def answer_correct(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    """The calibrated quiz judge, on handbook rows. Desk rows stay on code checks."""
    from evals.judge import final_answer_correct

    if not reference_outputs.get("response"):
        return {"key": "answer_correct", "score": None, "comment": "desk row: code checks only"}
    # The free judge model sometimes answers with no choices. Try three times, then let it error.
    for attempt in range(3):
        try:
            ok = final_answer_correct(inputs, outputs, reference_outputs)
            break
        except Exception:
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))
    return {"key": "answer_correct", "score": None if ok is None else int(ok)}


def reply_language(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    """A Spanish case must get a Spanish reply (issue #81). English rows are skipped."""
    from northstar.language import is_spanish

    if reference_outputs.get("language", "en") != "es":
        return {"key": "reply_language", "score": None, "comment": "English row"}
    return {"key": "reply_language", "score": int(is_spanish(outputs["response"]))}


def photo_verdict(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    """The photo line says what the labeled photo shows (issue #80). Rows without a photo are skipped."""
    wanted = reference_outputs.get("photo_verdict")
    if not wanted:
        return {"key": "photo_verdict", "score": None, "comment": "no photo"}
    return {"key": "photo_verdict", "score": int(f"Photo: {wanted}." in outputs["response"]), "comment": f"wanted {wanted}"}


def correct(inputs: dict, outputs: dict, reference_outputs: dict) -> bool:
    return outputs["route"] == reference_outputs["route"]


def code_scores(inputs: dict, outputs: dict, reference_outputs: dict) -> list[dict]:
    """Every code check of a row from one evaluator, so a row adds one evaluator trace, not five.

    The scores keep their own names. https://docs.langchain.com/langsmith/multiple-scores
    """
    checks = (label_match, citation_valid, status_correct, reply_language, photo_verdict)
    return [check(inputs, outputs, reference_outputs) for check in checks]


E2E_EVALUATORS = [code_scores, answer_correct]


# Commands -----------------------------------------------------------------


def _means(results) -> dict[str, float]:
    scores: dict[str, list[float]] = {}
    for row in results:
        for result in row["evaluation_results"]["results"]:
            if result.score is not None:
                scores.setdefault(result.key, []).append(float(result.score))
    return {key: round(sum(values) / len(values), 3) for key, values in sorted(scores.items())}


def _misses(results) -> list[str]:
    missed = []
    for row in results:
        for result in row["evaluation_results"]["results"]:
            if result.score == 0:
                missed.append(f"{row['example'].metadata['case_id']}: {result.key} ({result.comment or 'no comment'})")
    return sorted(set(missed))


def _section(name: str, results) -> list[str]:
    lines = [f"### {name}: `{results.experiment_name}`", "", f"Mean scores: {_means(results)}", "", "Misses:"]
    return lines + ([f"- {miss}" for miss in _misses(results)] or ["- none"]) + [""]


def gate_row(row) -> dict:
    """One recorded experiment row as the release bar reads it: the labels, the scores, the seconds, the tokens."""
    outputs, wanted = row["run"].outputs, row["example"].outputs
    scores = {result.key: result.score for result in row["evaluation_results"]["results"]}
    return {
        "passed": scores.get("label_match") == 1 and scores.get("status_correct") != 0,
        "decision": outputs["decision"],
        "wanted": wanted["decision"],
        "citations": list(outputs["citations"]),
        "bad_citation": scores.get("citation_valid") == 0,
        "ticket": bool(outputs.get("ticket")),
        "seconds": outputs["seconds"],
        "tokens": outputs["tokens"],
        "language": wanted.get("language", "en"),
    }


def _evaluate(client, target, upload: bool, **kwargs):
    """One experiment. Without upload, LangSmith gets no experiment, no feedback, and no trace."""
    if upload:
        return client.evaluate(target, upload_results=True, **kwargs)
    from langsmith import tracing_context

    # upload_results=False still posts the LangChain model runs inside the target and the evaluators
    # (langsmith 0.14.4), so a local check also turns tracing off around both.
    def untraced(inputs: dict) -> dict:
        with tracing_context(enabled=False):
            return target(inputs)

    return client.evaluate(untraced, upload_results=False, disable_evaluator_tracing=True, **kwargs)


def run(
    client,
    split: str,
    repetitions: int = 1,
    tag: str = "slice1",
    judge: bool = True,
    version: str | None = None,
    upload: bool = True,
    router: bool = False,
) -> tuple[str, list[dict]]:
    """The report, and the live desk's rows for the release bar."""
    if judge and split == "test" and not judges_may_score_test(Path("results/judge_calibration.md").read_text()):
        raise SystemExit("the judge is not calibrated for the test split")
    data = list(client.list_examples(dataset_name=E2E, splits=[split], as_of=tag))
    if version:
        data = [example for example in data if example.metadata.get("version") == version]
    evaluators = E2E_EVALUATORS if judge else [e for e in E2E_EVALUATORS if e is not answer_correct]
    judged = "with the quiz judge" if judge else "code checks only, no judge"
    uploaded = "" if upload else ", not uploaded"
    lines = [f"## {split} split, dataset tag {tag}, {len(data)} cases, {repetitions} repetition(s), {judged}{uploaded}", ""]
    rows: list[dict] = []
    desk = Desk()
    try:
        for name, target, concurrency in (("v0", v0, 4), ("v1", desk, 1)):
            results = _evaluate(
                client,
                target,
                upload,
                data=data,
                evaluators=evaluators,
                experiment_prefix=f"northstar-{name}-{split}",
                metadata={"version": name, "split": split, "dataset_tag": tag},
                num_repetitions=repetitions,
                max_concurrency=concurrency,
            )
            lines += _section(name, results)
            if target is desk:
                rows += [gate_row(row) for row in results]
    finally:
        desk.close()
    if router:
        routed = _evaluate(client, route, upload, data=INTENT, evaluators=[correct], experiment_prefix="northstar-router")
        lines += _section("router", routed)
    return "\n".join(lines), rows


def release(client, commit: str, tag: str = "slice1", judge: bool = True, upload: bool = True) -> tuple[str, dict]:
    """The release run: test with three repetitions, then the Spanish turns on the live desk.

    The Spanish cases sit in dev (the test split has none), so they count only toward their own latency
    target and the zero-tolerance gates, never toward action correct. They get code checks only, no judge.
    """
    from evals.release_bar import record

    report, rows = run(client, "test", RELEASE_REPETITIONS, tag, judge=judge, upload=upload)
    spanish = [e for e in client.list_examples(dataset_name=E2E, splits=["dev"], as_of="slice3-es") if e.metadata.get("version") == "slice3-es"]
    desk = Desk()
    try:
        results = _evaluate(
            client,
            desk,
            upload,
            data=spanish,
            evaluators=[code_scores],
            experiment_prefix="northstar-v1-es-dev",
            metadata={"version": "v1", "split": "dev", "dataset_tag": "slice3-es"},
            num_repetitions=RELEASE_REPETITIONS,
            max_concurrency=1,
        )
    finally:
        desk.close()
    rows += [gate_row(row) for row in results]
    bar = {**record(rows, commit), "uploaded": upload}
    lines = [report, f"## Release bar on {commit}", "", f"{len(spanish)} Spanish cases from dev, {RELEASE_REPETITIONS} repetition(s).", ""]
    lines += _section("v1 Spanish turns", results)
    lines += [f"Gates: {bar['gates']}", "", f"Measured: {bar['measured']}", ""]
    return "\n".join(lines), bar


def measured_commit() -> str:
    """The commit a release run measures. Uncommitted code changes would make that name untrue."""

    def git(*args: str) -> str:
        return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout

    changed = [line[3:] for line in git("status", "--porcelain", "--untracked-files=no").splitlines()]
    code = [path for path in changed if not path.startswith("results/")]
    if code:
        raise SystemExit(f"commit or stash these first, so the results file names the code it measured: {code}")
    return git("rev-parse", "HEAD").strip()


def promote(client, run_id: str, decision: str, sections: list[str], split: str, status: str | None) -> str:
    """A person adds one reviewed specialist edit as a labeled case, under a new dataset version.

    The corrected text becomes the reference. Nothing here changes the handbook or a rule.
    """
    from evals.labeled import registry_ids

    unknown = [section for section in sections if section not in registry_ids()]
    if unknown:
        raise SystemExit(f"unknown sections {unknown}")
    edits = [fb for fb in client.list_feedback(run_ids=[run_id], feedback_key=["specialist_edit"]) if fb.correction]
    if not edits:
        raise SystemExit("that run has no specialist edit")
    question = client.read_run(run_id).inputs["question"]  # read_run is the stable sync call in this SDK
    case_id = f"edit-{run_id[:8]}"
    tag = f"edit-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"
    example = {
        "id": _example_id(case_id),
        "inputs": {"question": question, "customer": None, "advance_days": 0},
        "outputs": {
            "decision": decision,
            "sections": sections,
            "status": status,
            "response": edits[-1].correction["followup"],
            "text_includes": [],
            "text_excludes": [],
        },
        "metadata": {"case_id": case_id, "channel": "desk" if status else "handbook", "version": tag, "source_run": run_id},
        "split": split,
    }
    added = _add(client, E2E, "", [example], tag)
    return f"{case_id} added under tag {tag}" if added else f"{case_id} is already in the dataset"


def main(argv: list[str] | None = None) -> None:
    root = Path(__file__).resolve().parents[1]
    sys.path[:0] = [str(root / "apps/api"), str(root / "apps/api/tests")]
    from langsmith import Client
    from northstar.agent_model import _load_local_env

    _load_local_env()
    parser = argparse.ArgumentParser(prog="evals.experiments")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("sync")
    ran = commands.add_parser("run")
    ran.add_argument("--split", default="test", choices=("train_judge", "dev", "test"))
    ran.add_argument("--repetitions", type=int, default=1, help="3 for the release run on test")
    ran.add_argument("--tag", default="slice1")
    ran.add_argument("--no-judge", action="store_true", help="code checks only, when the judge model is unavailable")
    ran.add_argument("--version", help="only the examples added under this version, for example slice3-photo")
    ran.add_argument("--no-upload", action="store_true", help="a local check: nothing is uploaded to LangSmith, no results file")
    ran.add_argument("--router", action="store_true", help="also run the router experiment, when routing changed")
    released = commands.add_parser("release", help="the release bar before a promotion into uat")
    released.add_argument("--tag", default="slice1")
    released.add_argument("--no-judge", action="store_true", help="code checks only, when the judge model is unavailable")
    released.add_argument("--no-upload", action="store_true", help="nothing uploaded to LangSmith; the results file is still written")
    promoted = commands.add_parser("promote")
    promoted.add_argument("run_id")
    promoted.add_argument("--decision", required=True)
    promoted.add_argument("--sections", default="")
    promoted.add_argument("--split", default="dev", choices=("dev", "test"))
    promoted.add_argument("--status")
    args = parser.parse_args(argv)
    client = Client()
    if args.command == "sync":
        sync(client)
    elif args.command == "release":
        commit = measured_commit()
        report, bar = release(client, commit, args.tag, judge=not args.no_judge, upload=not args.no_upload)
        print(report)
        if not args.no_upload:
            Path("results/langsmith_test.md").write_text("# LangSmith experiments\n\n" + report)
        RELEASE_FILE.write_text(json.dumps(bar, indent=2) + "\n")
        print(f"{RELEASE_FILE}: {'passed' if all(bar['gates'].values()) else 'FAILED'}. Commit it, then open the PR into uat.")
    elif args.command == "run":
        report, _ = run(
            client,
            args.split,
            args.repetitions,
            args.tag,
            judge=not args.no_judge,
            version=args.version,
            upload=not args.no_upload,
            router=args.router,
        )
        print(report)
        # A local check names experiments that LangSmith never saw, so it leaves the results files alone.
        if not args.no_upload:
            Path(f"results/langsmith_{args.split}{'_' + args.version if args.version else ''}.md").write_text("# LangSmith experiments\n\n" + report)
    else:
        sections = [section for section in args.sections.split(",") if section]
        print(promote(client, args.run_id, args.decision, sections, args.split, args.status))


if __name__ == "__main__":
    main()
